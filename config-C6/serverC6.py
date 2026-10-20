import threading
import queue
import time

fila_requisicoes = queue.Queue(maxsize=2) # só aceita 2 perguntas por vez
mutex_log = threading.Lock()

def registrar_log(mensagem):
    timestamp = time.strftime("%H:%M:%S")
    with mutex_log:
        with open("c6.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {mensagem}\n")
    print(f"[{timestamp}] {mensagem}")


def trabalhador_consumidor(id_thread):
    while True:
        try:
            consulta = fila_requisicoes.get(timeout=5)
            registrar_log(f"[Trabalhador {id_thread}] Retirou da fila e começou: '{consulta}'")
            
            # Simulando processamento lento
            time.sleep(3) 
            
            registrar_log(f"[Trabalhador {id_thread}] Terminou: '{consulta}'")
            fila_requisicoes.task_done()
            
        except queue.Empty:
            registrar_log(f"[Trabalhador {id_thread}] Fila vazia há muito tempo. Encerrando.")
            break

if __name__ == "__main__":
    registrar_log("--- INICIANDO TESTE C6: FALHA CONTROLADA POR FILA SATURADA ---")
    
    # Inicia 2 Trabalhadores lentos
    threads = []
    for i in range(2): 
        t = threading.Thread(target=trabalhador_consumidor, args=(i+1,))
        t.start()
        threads.append(t)
        
    # produtor tenta "soterrar" o sistema mandando 6 perguntas muito rápido
    for i in range(1, 7):
        pergunta = f"Pergunta número {i}"
        registrar_log(f"[Produtor] Tentando inserir '{pergunta}'...")
        
        try:
            # O timeout=1 força o erro se a fila (maxsize=2) ficar cheia por mais de 1 segundo
            fila_requisicoes.put(pergunta, timeout=1)
            registrar_log(f"[Produtor] SUCESSO: '{pergunta}' aceita pelo servidor!")
            
        except queue.Full:
            # A FALHA CONTROLADA: Captura a saturação e rejeita o pedido em vez de travar o servidor
            registrar_log(f"FALHA CONTROLADA C6: Fila saturada! Rejeitando a '{pergunta}' por excesso de carga.")
            
    registrar_log("[Produtor] Envio de requisições finalizado. Aguardando processamento do que foi aceito...")
    
    # aguarda o encerramento limpo das requisições que conseguiram entrar
    fila_requisicoes.join()
    for t in threads:
        t.join()
        
    registrar_log("--- TESTE C6 FINALIZADO ---")
