import os
import time
import mmap
import threading
import queue
import requests
import json

# =====================================================================
# CONFIGURAÇÕES GLOBAIS E ESTRUTURAS COMPARTILHADAS
# =====================================================================
ARQUIVO_LOG = "auditoria_genresearch.log"

# Fila thread-safe do Python (bloqueante se encher ou esvaziar)
fila_requisicoes = queue.Queue(maxsize=10)

# Estruturas em memória RAM e seus respectivos Mutexes (Locks)
cache_compartilhado = {}
lock_cache = threading.Lock()
lock_log = threading.Lock()

# =====================================================================
# MÓDULO 1: INGESTÃO E ARMAZENAMENTO (C1 e C2)
# =====================================================================
def ler_arquivo_convencional(caminho_arquivo):
    """C1: Lê o arquivo usando open() e read()."""
    inicio = time.time()
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        dados = f.read()
    tempo_decorrido = time.time() - inicio
    print(f"[Ingestão] Leitura Convencional concluída em {tempo_decorrido:.4f}s")
    return dados

def ler_arquivo_mmap(caminho_arquivo):
    """C2: Mapeia o arquivo direto na memória virtual do SO usando mmap."""
    inicio = time.time()
    with open(caminho_arquivo, "r+b") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            dados = mm.read()
    tempo_decorrido = time.time() - inicio
    print(f"[Ingestão] Leitura por MMAP concluída em {tempo_decorrido:.4f}s")
    return dados

# =====================================================================
# MÓDULOS 4 E 6: CACHE E LOGS COM SINCRONIZAÇÃO (PARTE D)
# =====================================================================
def registrar_log(mensagem):
    """Escreve eventos de forma segura no arquivo de log (Região Crítica)."""
    agora = time.strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] {mensagem}\n"
    
    with lock_log: # Adquire o Mutex antes de escrever
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(linha)

def buscar_no_cache(pergunta):
    """Busca a resposta no cache protegendo a leitura."""
    with lock_cache:
        if pergunta in cache_compartilhado:
            return cache_compartilhado[pergunta]
        return None

def salvar_no_cache(pergunta, resposta):
    """Salva a resposta no cache protegendo a escrita (Região Crítica)."""
    with lock_cache:
        cache_compartilhado[pergunta] = resposta

# =====================================================================
# MÓDULO 5: RESPOSTA (MISTRAL 7B VIA OLLAMA)
# =====================================================================
def gerar_resposta_ollama(contexto_recuperado, pergunta):
    """Faz a requisição HTTP local para o modelo."""
    url = "http://localhost:11434/api/generate"
    prompt_final = f"Baseado no texto: '{contexto_recuperado}', responda: {pergunta}"
    
    payload = {
        "model": "mistral",
        "prompt": prompt_final,
        "stream": False,
        "options": {
            "num_predict": 100,
            "temperature": 0.0
        }
    }
    
    inicio = time.time()
    try:
        response = requests.post(url, json=payload)
        dados = response.json()
        tempo_cpu = dados.get('eval_duration', 0) / 1e9
        resposta_texto = dados.get('response', '').strip()
        return resposta_texto, tempo_cpu
    except Exception as e:
        return f"Erro ao conectar com Ollama: {e}", 0

# =====================================================================
# TRABALHADORES E PRODUTORES (MÓDULOS 2 E 3 - PARTE C.3)
# =====================================================================
def trabalhador_consumidor(id_trabalhador):
    """Retira da fila, checa cache, simula recuperação, chama IA e loga."""
    while True:
        try:
            pergunta = fila_requisicoes.get(timeout=3)
            registrar_log(f"[Trabalhador {id_trabalhador}] Iniciou processamento da '{pergunta}'")
            
            # Checa o Cache (Configuração C4)
            resposta_cache = buscar_no_cache(pergunta)
            
            if resposta_cache:
                registrar_log(f"[Trabalhador {id_trabalhador}] Acerto de Cache (Hit) para '{pergunta}'")
                print(f"[Trabalhador {id_trabalhador}] Respondeu via Cache: '{pergunta}'")
            else:
                registrar_log(f"[Trabalhador {id_trabalhador}] Erro de Cache (Miss). Buscando contexto...")
                contexto_falso = "O sistema operacional é o principal orquestrador de hardware."
                
                print(f"[Trabalhador {id_trabalhador}] Chamando Mistral para '{pergunta}'...")
                resposta_ia, tempo = gerar_resposta_ollama(contexto_falso, pergunta)
                
                salvar_no_cache(pergunta, resposta_ia)
                registrar_log(f"[Trabalhador {id_trabalhador}] Resposta gerada em {tempo:.2f}s e salva no cache.")
            
            fila_requisicoes.task_done()
            
        except queue.Empty:
            print(f"[Trabalhador {id_trabalhador}] Fila vazia, encerrando.")
            break

def produtor(id_produtor, num_mensagens):
    """Gera requisições e as insere na fila bloqueante."""
    for i in range(num_mensagens):
        # Para testar o cache (C4), o produtor 1 manda perguntas repetidas.
        if id_produtor == 1:
            pergunta = "O que é um sistema operacional?"
        else:
            pergunta = f"Consulta {i} gerada pelo Produtor {id_produtor}"
            
        fila_requisicoes.put(pergunta)
        registrar_log(f"[Produtor {id_produtor}] Adicionou: '{pergunta}' à fila.")
        time.sleep(0.5)

# =====================================================================
# BLOCO PRINCIPAL (ORQUESTRADOR DOS EXPERIMENTOS)
# =====================================================================
if __name__ == "__main__":
    # Limpa o arquivo de log a cada nova execução
    open(ARQUIVO_LOG, 'w').close()
    print("Iniciando GenResearch-Servidor...\n")
    
    # -----------------------------------------------------------------
    # EXPERIMENTO 1: Leitura (Comente esta seção se não for testar o mmap agora)
    # -----------------------------------------------------------------
    ARQUIVO_CORPUS = "corpus_teste.txt"
    if os.path.exists(ARQUIVO_CORPUS):
        print("--- Teste de Ingestão de Arquivo ---")
        ler_arquivo_convencional(ARQUIVO_CORPUS)
        ler_arquivo_mmap(ARQUIVO_CORPUS)
        print("-" * 36 + "\n")
    else:
        print(f"Aviso: Arquivo '{ARQUIVO_CORPUS}' não encontrado. Pulando teste de ingestão.\n")

    # -----------------------------------------------------------------
    # EXPERIMENTO 2: Concorrência, Filas e IA (C3 e C4)
    # -----------------------------------------------------------------
    NUM_PRODUTORES = 2
    NUM_TRABALHADORES = 4 # Variável de controle do experimento (Testar 1, 2 e 4)
    MENSAGENS_POR_PRODUTOR = 3
    
    threads = []
    
    print(f"--- Iniciando Bateria de Testes (Trabalhadores: {NUM_TRABALHADORES}) ---")
    
    # Instancia as Threads Consumidoras
    for i in range(NUM_TRABALHADORES):
        t = threading.Thread(target=trabalhador_consumidor, args=(i+1,))
        t.start()
        threads.append(t)
        
    # Instancia as Threads Produtoras
    for i in range(NUM_PRODUTORES):
        t = threading.Thread(target=produtor, args=(i+1, MENSAGENS_POR_PRODUTOR))
        t.start()
        threads.append(t)
        
    # Aguarda todas as threads finalizarem
    for t in threads:
        t.join()
        
    print("\nExecução finalizada. Verifique o arquivo 'auditoria_genresearch.log' para os resultados completos.")