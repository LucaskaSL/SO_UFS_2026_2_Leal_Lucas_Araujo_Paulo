import sqlite3
import threading
import queue
import time
import random
import requests
import os

ARQUIVO_LOG = "execucao_c4.log"
MODELO_OLLAMA = "mistral"
ARQUIVO_CORPUS = "corpus_padrao.txt" 

fila_requisicoes = queue.Queue(maxsize=10)
cache_compartilhado = {}
mutex_log = threading.Lock()
mutex_cache = threading.Lock()

def registrar_log(mensagem):
    timestamp = time.strftime("%H:%M:%S")
    with mutex_log:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {mensagem}\n")
    print(f"[{timestamp}] {mensagem}")

def preparar_banco(caminho_arquivo):
    conexao = sqlite3.connect("genresearch_c4.db")
    cursor = conexao.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documentos 
                      (id INTEGER PRIMARY KEY, trecho TEXT, vetor TEXT)''')
    
    if not os.path.exists(caminho_arquivo):
        registrar_log(f"ERRO: Arquivo {caminho_arquivo} não encontrado.")
        return conexao

    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    
    fragmentos = [conteudo[i:i+1000] for i in range(0, len(conteudo), 1000)]
    cursor.execute("DELETE FROM documentos") 
    
    for trecho in fragmentos:
        vetor_simulado = str([round(random.uniform(-1.0, 1.0), 4) for _ in range(3)])
        cursor.execute("INSERT INTO documentos (trecho, vetor) VALUES (?, ?)", (trecho, vetor_simulado))
        
    conexao.commit()
    registrar_log(f"Ingestão: {len(fragmentos)} fragmentos armazenados.")
    return conexao

def gerar_resposta_ollama(pergunta, contexto):
    prompt = f"Baseado no contexto: '{contexto}'. Responda de forma resumida: {pergunta}"
    url = "http://localhost:11434/api/generate"
    payload = {"model": MODELO_OLLAMA, "prompt": prompt, "stream": False}
    
    try:
        resposta = requests.post(url, json=payload)
        return resposta.json().get("response", "Erro na resposta vazia.")
    except Exception as e:
        return f"Falha de comunicação: {e}"

def trabalhador_consumidor(id_thread):
    conexao = sqlite3.connect("genresearch_c4.db")
    cursor = conexao.cursor()
    
    while True:
        try:
            consulta = fila_requisicoes.get(timeout=3)
            inicio = time.time()
            registrar_log(f"[Thread {id_thread}] Processando: '{consulta}'")
            
            resposta_final = None
            
            # --- PROTEÇÃO DO CACHE (Mutéx) ---
            with mutex_cache:
                if consulta in cache_compartilhado:
                    resposta_final = cache_compartilhado[consulta]
                    registrar_log(f"[Thread {id_thread}] ACERTO NO CACHE (Hit) para '{consulta}'")
                else:
                    registrar_log(f"[Thread {id_thread}] FALTA NO CACHE (Miss) para '{consulta}'. Consultando modelo...")
            
            # --- PROCESSAMENTO (Apenas se falhou no cache) ---
            if not resposta_final:
                cursor.execute("SELECT trecho FROM documentos ORDER BY RANDOM() LIMIT 1")
                contexto_recuperado = cursor.fetchone()[0]
                resposta_final = gerar_resposta_ollama(consulta, contexto_recuperado)
                
                with mutex_cache:
                    cache_compartilhado[consulta] = resposta_final
                    
            tempo_total = time.time() - inicio
            registrar_log(f"[Thread {id_thread}] Concluiu em {tempo_total:.2f}s. Resposta: {resposta_final}...")
            fila_requisicoes.task_done()
            
        except queue.Empty:
            conexao.close()
            break

if __name__ == "__main__":
    open(ARQUIVO_LOG, "w").close() 
    registrar_log("Inicio do log.")
    preparar_banco(ARQUIVO_CORPUS)
    
    threads = []
    for i in range(2): 
        t = threading.Thread(target=trabalhador_consumidor, args=(i+1,))
        t.start()
        threads.append(t)
        
    # ATENÇÃO: As duas últimas perguntas são iguais às duas primeiras para forçar o Acerto (Hit)
    perguntas = [
        "Quem é Pierre Bezúkhov e como a sua visão muda?",
        "Qual é o impacto da invasão de Napoleão?",
        "Descreva a relação entre Natasha e Andrei.",
        "Descreva a relação entre Natasha e Andrei.", # HIT
        "Quem é Pierre Bezúkhov e como a sua visão muda?", # HIT
        "Qual é o impacto da invasão de Napoleão?" # HIT
    ]
    
    for p in perguntas:
        fila_requisicoes.put(p)
        time.sleep(0.5) 
        
    fila_requisicoes.join()
    for t in threads:
        t.join()
    registrar_log("TESTE C4 FINALIZADO")
