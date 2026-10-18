import sqlite3
import threading
import queue
import time
import random
import requests
import os
import mmap

# --- Recursos Compartilhados e Travas (Mutex) ---
fila_requisicoes = queue.Queue(maxsize=10)
cache_compartilhado = {}
mutex_log = threading.Lock()
mutex_cache = threading.Lock()

ARQUIVO_LOG = "execucao.log" # nome do arquivo que o log será escrito
MODELO_OLLAMA = "mistral"    # nome do modelo chamado pelo ollama
NOME_CORPUS = "corpus_padrao.txt"   # nome do arquivo do corpus

def registrar_log(mensagem):
    timestamp = time.strftime("%H:%M:%S")
    with mutex_log:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {mensagem}\n")
    print(f"[{timestamp}] {mensagem}")

# --- Ingestão e Armazenamento (SQLite) ---
def preparar_banco(caminho_arquivo):
    conexao = sqlite3.connect("genresearch.db")
    cursor = conexao.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documentos 
                      (id INTEGER PRIMARY KEY, trecho TEXT, vetor TEXT)''')
    
    cursor.execute("DELETE FROM documentos") # Limpa testes anteriores

    tamanho_chunk = 1000
    fragmentos_count = 0

    # Abertura em modo leitura binária para uso com mmap
    with open(caminho_arquivo, "rb") as f:
        # Se o arquivo estiver vazio, evita erro no mmap
        tamanho_arquivo = os.path.getsize(caminho_arquivo)
        if tamanho_arquivo == 0:
            registrar_log("Ingestão: Arquivo corpus está vazio.")
            return conexao

        # Cria a visualização mapeada em memória (modo SOMENTE LEITURA)
        with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            # Itera em blocos de 1000 bytes
            for i in range(0, tamanho_arquivo, tamanho_chunk):
                # Extrai a fatia diretamente do mapa de memória
                bloco_bytes = mm[i:i + tamanho_chunk]
                
                # Decodifica bytes para string UTF-8
                trecho = bloco_bytes.decode('utf-8', errors='ignore')
                
                vetor_simulado = str([round(random.uniform(-1.0, 1.0), 4) for _ in range(3)])
                cursor.execute("INSERT INTO documentos (trecho, vetor) VALUES (?, ?)", (trecho, vetor_simulado))
                fragmentos_count += 1
        
    conexao.commit()
    registrar_log(f"Ingestão (mmap): {fragmentos_count} fragmentos armazenados no SQLite.")
    return conexao 
# --- Integração com Ollama ---
def gerar_resposta_ollama(pergunta, contexto):
    prompt = f"Baseado no contexto: '{contexto}'. Responda: {pergunta}"
    url = "http://localhost:11434/api/generate"
    payload = {"model": MODELO_OLLAMA, "prompt": prompt, "stream": False}
    
    try:
        resposta = requests.post(url, json=payload)
        return resposta.json().get("response", "Erro na resposta vazia.")
    except Exception as e:
        return f"Falha de comunicação com Ollama: {e}"

# --- Trabalhador (Consumidor) ---
def trabalhador_consumidor(id_thread):
    conexao = sqlite3.connect("genresearch.db")
    cursor = conexao.cursor()
    
    while True:
        try:
            consulta = fila_requisicoes.get(timeout=3)
            inicio = time.time()
            registrar_log(f"[Thread {id_thread}] Processando: '{consulta}'")
            
            # Verifica o Cache de forma segura
            resposta_final = None
            with mutex_cache:
                if consulta in cache_compartilhado:
                    resposta_final = cache_compartilhado[consulta]
                    registrar_log(f"[Thread {id_thread}] RESPOSTA NO CACHE para '{consulta}'")
            
            # Se não estiver no cache, recupera contexto e chama o modelo
            if not resposta_final:
                # Recuperação simulada: pega um trecho aleatório do banco
                cursor.execute("SELECT trecho FROM documentos ORDER BY RANDOM() LIMIT 1")
                contexto_recuperado = cursor.fetchone()[0]
                
                resposta_final = gerar_resposta_ollama(consulta, contexto_recuperado)
                
                # Salva no cache de forma segura
                with mutex_cache:
                    cache_compartilhado[consulta] = resposta_final
                    
            tempo_total = time.time() - inicio
            registrar_log(f"[Thread {id_thread}] Concluiu em {tempo_total:.2f}s. Resposta: {resposta_final}...")
            fila_requisicoes.task_done()
            
        except queue.Empty:
            registrar_log(f"[Thread {id_thread}] Fila vazia, encerrando.")
            conexao.close()
            break

# --- Execução Principal ---
if __name__ == "__main__":
    open(ARQUIVO_LOG, "w").close() # Limpa log antigo
    
    preparar_banco(NOME_CORPUS)
    
    # Inicia Threads
    threads = []
    for i in range(2): # 2 trabalhadores para começar
        t = threading.Thread(target=trabalhador_consumidor, args=(i+1,))
        t.start()
        threads.append(t)
        
    perguntas = ["Quem é Pierre Bezúkhov e como a sua visão de mundo muda ao longo da história?",
                 "Qual é o impacto da invasão de Napoleão na sociedade aristocrática russa?",
                 "Descreva a relação entre Natasha Rostova e o príncipe Andrei Bolkonsky."]
    for p in perguntas:
        fila_requisicoes.put(p)
        
    fila_requisicoes.join()
    for t in threads:
        t.join()
        
    registrar_log("Servidor GenResearch finalizado com sucesso.")
