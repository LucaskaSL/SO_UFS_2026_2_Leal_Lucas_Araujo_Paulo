import sqlite3
import threading
import queue
import time
import random
import requests
import os

# --- Recursos Compartilhados e Travas (Mutex) ---
fila_requisicoes = queue.Queue(maxsize=10)
cache_compartilhado = {}
mutex_log = threading.Lock()
mutex_cache = threading.Lock()

ARQUIVO_LOG = "execucao.log"
MODELO_OLLAMA = "mistral"
NOME_CORPUS = "corpus_padrao.txt"

def registrar_log(mensagem):
    timestamp = time.strftime("%H:%M:%S")
    with mutex_log:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {mensagem}\n")
    print(f"[{timestamp}] {mensagem}")

# --- Ingestão e Armazenamento (Leitura Convencional sem mmap) ---
def preparar_banco(caminho_arquivo):
    conexao = sqlite3.connect("genresearch.db")
    cursor = conexao.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documentos 
                      (id INTEGER PRIMARY KEY, trecho TEXT, vetor TEXT)''')
    cursor.execute("DELETE FROM documentos")

    tamanho_chunk = 1000
    fragmentos_count = 0

    if not os.path.exists(caminho_arquivo):
        # Cria arquivo de teste caso não exista
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write("Guerra e Paz. " * 500)

    # Leitura sequencial do arquivo em blocos de caracteres
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        while True:
            trecho = f.read(tamanho_chunk)
            if not trecho:
                break  # Fim do arquivo
            
            vetor_simulado = str([round(random.uniform(-1.0, 1.0), 4) for _ in range(3)])
            cursor.execute("INSERT INTO documentos (trecho, vetor) VALUES (?, ?)", (trecho, vetor_simulado))
            fragmentos_count += 1

    conexao.commit()
    conexao.close()
    registrar_log(f"Ingestão (Stream): {fragmentos_count} fragmentos armazenados no SQLite.")

# --- Integração com Ollama ---
def gerar_resposta_ollama(pergunta, contexto):
    prompt = f"Baseado no contexto: '{contexto}'. Responda: {pergunta}"
    url = "http://localhost:11434/api/generate"
    payload = {"model": MODELO_OLLAMA, "prompt": prompt, "stream": False}
    
    try:
        resposta = requests.post(url, json=payload, timeout=10)
        return resposta.json().get("response", "Erro na resposta vazia.")
    except Exception as e:
        return f"Falha de comunicação com Ollama: {e}"

# --- Produtor (Gerador de Requisições) ---
def trabalhador_produtor(id_produtor, lista_perguntas):
    for pergunta in lista_perguntas:
        time.sleep(random.uniform(0.1, 0.5))  # Simula intervalo entre requisições
        registrar_log(f"[Produtor {id_produtor}] Enviando pergunta: '{pergunta}'")
        fila_requisicoes.put(pergunta)
    registrar_log(f"[Produtor {id_produtor}] Finalizou o envio das suas requisições.")

# --- Consumidor (Processador de Requisições) ---
def trabalhador_consumidor(id_consumidor):
    conexao = sqlite3.connect("genresearch.db")
    cursor = conexao.cursor()
    
    while True:
        consulta = fila_requisicoes.get()
        
        # Sinal de parada (Sentinel Value / Poison Pill)
        if consulta is None:
            registrar_log(f"[Consumidor {id_consumidor}] Recebeu sinal de encerramento.")
            fila_requisicoes.task_done()
            break

        inicio = time.time()
        registrar_log(f"[Consumidor {id_consumidor}] Processando: '{consulta}'")
        
        # 1. Checa o Cache de forma segura
        resposta_final = None
        with mutex_cache:
            if consulta in cache_compartilhado:
                resposta_final = cache_compartilhado[consulta]
                registrar_log(f"[Consumidor {id_consumidor}] RESPOSTA NO CACHE para '{consulta}'")
        
        # 2. Busca contexto no banco e chama a API caso não esteja em cache
        if not resposta_final:
            cursor.execute("SELECT trecho FROM documentos ORDER BY RANDOM() LIMIT 1")
            resultado = cursor.fetchone()
            contexto_recuperado = resultado[0] if resultado else "Sem contexto."
            
            resposta_final = gerar_resposta_ollama(consulta, contexto_recuperado)
            
            with mutex_cache:
                cache_compartilhado[consulta] = resposta_final
                
        tempo_total = time.time() - inicio
        registrar_log(f"[Consumidor {id_consumidor}] Concluiu em {tempo_total:.2f}s. Resposta: {resposta_final[:60]}...")
        fila_requisicoes.task_done()
        
    conexao.close()

# --- Execução Principal ---
if __name__ == "__main__":
    open(ARQUIVO_LOG, "w").close()  # Limpa log antigo
    preparar_banco(NOME_CORPUS)
    
    # Listas de perguntas atribuídas a cada produtor
    perguntas_produtor_1 = [
        "Quem é Pierre Bezúkhov e como a sua visão de mundo muda ao longo da história?",
        "Qual é o impacto da invasão de Napoleão na sociedade aristocrática russa?",
        "Quem é Pierre Bezúkhov e como a sua visão de mundo muda ao longo da história?"  # Teste de Cache
    ]
    
    perguntas_produtor_2 = [
        "Descreva a relação entre Natasha Rostova e o príncipe Andrei Bolkonsky.",
        "Qual é o impacto da invasão de Napoleão na sociedade aristocrática russa?",  # Teste de Cache
        "Qual o papel do General Kutuzov na estratégia de defesa russa?"
    ]

    produtores = []
    consumidores = []

    # 1. Inicializa 2 Consumidores
    for i in range(2):
        t = threading.Thread(target=trabalhador_consumidor, args=(i + 1,))
        t.start()
        consumidores.append(t)

    # 2. Inicializa 2 Produtores
    t_p1 = threading.Thread(target=trabalhador_produtor, args=(1, perguntas_produtor_1))
    t_p2 = threading.Thread(target=trabalhador_produtor, args=(2, perguntas_produtor_2))
    
    produtores.extend([t_p1, t_p2])
    t_p1.start()
    t_p2.start()

    # 3. Aguarda os produtores terminarem de enviar
    for p in produtores:
        p.join()

    # 4. Aguarda o consumo de todas as perguntas
    fila_requisicoes.join()

    # 5. Envia os sinais de encerramento (um para cada consumidor)
    for _ in range(2):
        fila_requisicoes.put(None)

    # 6. Aguarda a finalização das threads consumidoras
    for c in consumidores:
        c.join()

    registrar_log("Servidor GenResearch finalizado com sucesso.")