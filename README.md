# GenResearch-Servidor

Este repositório contém a implementação do GenResearch-Servidor, um *pipeline* simplificado de Recuperação Aumentada por Geração (RAG) desenvolvido para observação e análise de recursos do sistema operacional, como memória, concorrência e armazenamento.

## Ambiente de Execução e Especificações

O ambiente base configurado para a validação e execução dos experimentos atende aos seguintes requisitos técnicos:

* **Sistema Operacional:** Linux Mint 22.3 (Nativo)
* **Kernel:** Linux 6.17.0-1033-oem
* **Processador (CPU):** Intel(R) Core(TM) Ultra 5 235U (14 núcleos, arquitetura x86_64)
* **Memória RAM e Swap:** 15 GiB de RAM e 2 GiB de *swap*
* **Armazenamento:** 476,9 GB (Sistema de arquivos ext4)
* **Aceleração Gráfica:** Sem GPU dedicada. A inferência do modelo é executada integralmente via CPU.
* **Linguagem e Bibliotecas:** Python 3.12.3 (`sqlite3`, `threading`, `queue`, `time`, `random`, `requests` e `os`)
* **Runtime de IA:** Ollama executando o modelo `Mistral-7B-Instruct-v0.3` quantizado (pesos reduzidos para aproximadamente 4.1 GB)

## Instalação e Configuração Prévia

Antes de executar os cenários, certifique-se de que o ambiente possui o Python e o Ollama configurados corretamente.

1. **Inicie o servidor local do Ollama:**
   O *script* espera que a API do Ollama esteja rodando localmente na porta padrão (`11434`).
   ```bash
   ollama serve
   ```

2. **Baixe o modelo Mistral quantizado:**
   ```bash
   ollama run mistral
   ```

3. **Prepare o Corpus:**
   Crie um arquivo chamado `corpus_padrao.txt` no mesmo diretório dos *scripts* com o conteúdo de texto que servirá de base de conhecimento para o servidor.

---

## Contexto 1: C1 - Leitura Convencional (Linha de Base)

O **Contexto 1** estabelece a linha de base do projeto, realizando a leitura convencional do arquivo de *corpus* através das funções padrão da linguagem (`open` e `read`). 

### Como funciona
* **Ingestão:** Lê o `corpus_padrao.txt`, fragmenta o texto em pedaços de 1.000 caracteres e os armazena em um banco de dados SQLite (`genresearch.db`), simulando *embeddings* aleatórios.
* **Concorrência:** Utiliza o padrão produtor-consumidor com uma fila de requisições (`queue.Queue`) limitada a 10 itens. Duas *threads* operam concorrentemente para retirar tarefas da fila e processá-las.
* **Sincronização:** Implementa *mutexes* (`threading.Lock`) para proteger as áreas críticas: gravação atômica no arquivo `execucao.log` (evitando intercalação de textos) e leitura/escrita no cache compartilhado em memória.
* **Cache:** Respostas já processadas são armazenadas. Se uma *thread* encontra a mesma pergunta no cache, a chamada custosa ao Ollama é evitada, economizando recursos computacionais.

### Como executar

Execute o arquivo correspondente ao Contexto 1 diretamente pelo terminal:

```bash
python3 server.py
```

**Resultados esperados:**
1. O arquivo `genresearch.db` será criado/sobrescrito com os trechos textuais fragmentados.
2. O arquivo `execucao.log` documentará o início das *threads*, o processamento das perguntas, o uso do cache e o encerramento seguro dos consumidores.
3. As respostas do modelo Mistral-7B-Instruct-v0.3 geradas via CPU (ou resgatadas do cache) aparecerão no *log* e no terminal.

## Contexto 2: C2 - Arquivo Mapeado (mmap) e Pressão de Memória

O **Contexto 2** modifica a forma como o sistema operacional lida com a leitura do arquivo de *corpus*. Em vez de carregar o texto inteiro para a memória da aplicação de uma só vez, ele utiliza a biblioteca `mmap` para criar um mapeamento direto do arquivo na memória virtual. Esta configuração também utiliza um arquivo de entrada maior (`corpus_exagerado.txt`) para observar o comportamento do sistema sob carga.

### Como funciona
*   **Mapeamento em Memória (mmap):** O arquivo é aberto em modo binário (`rb`) e fatiado diretamente da memória virtual em blocos de 1.000 bytes. O sistema operacional (Linux) gerencia o carregamento das páginas do disco para a RAM sob demanda, gerando faltas de página (*page faults*) apenas quando um bloco específico é acessado.
*   **Tratamento de Arquivos Grandes:** Essa abordagem previne o esgotamento imediato da RAM principal e evita a cópia redundante de dados entre o *kernel* e o espaço do usuário, sendo ideal para leitura de arquivos massivos ou *checkpoints* de modelos de IA.
*   **Concorrência e Cache Mantidos:** A estrutura de múltiplos consumidores, fila de tarefas limitadas e proteção por *mutexes* permanece idêntica ao Contexto 1, garantindo que a única variável independente testada seja a mecânica de Entrada/Saída e o tamanho do arquivo.

### Como executar

Antes de executar, você precisará de um *corpus* de texto substancialmente maior. 
1. Execute o *script* no terminal
```bash
python3 size_increase.py
```

vai criar arquivo grande chamado `corpus_exagerado.txt` no diretório.

2. Execute o *script* no terminal:

```bash
python3 serverC2.py
``` 

**Resultados esperados:**

Os dados de log serão agora redirecionados para execucao_exagerado.log.

Durante a primeira execução, ferramentas como `vmstat` ou `iostat -xz` em outro terminal devem registrar picos de faltas de página enquanto o SO carrega os blocos mapeados.

Em uma segunda execução imediata, o tempo de ingestão deve ser notavelmente menor, comprovando que o cache de páginas do Linux manteve o arquivo retido na RAM.

## Contexto 3: C3 - Concorrência e Fila (Produtores e Consumidores)

O **Contexto 3** implementa o cenário experimental focado na arquitetura de concorrência da aplicação, utilizando o modelo clássico de produtores e consumidores. Esta etapa avalia a capacidade do sistema operacional em coordenar o acesso a filas e recursos compartilhados, garantindo a exclusão mútua e prevenindo bloqueios indesejados.

### Como funciona
*   **Produtores e Consumidores:** O *pipeline* é dividido em papéis claros. Duas *threads* independentes assumem o papel de produtores, simulando a chegada de requisições em tempos aleatórios e inserindo consultas na fila. Simultaneamente, duas *threads* atuam como consumidoras (trabalhadores concorrentes), retirando as tarefas da fila para executar a recuperação no banco SQLite e a inferência no Ollama.
*   **Controle de Fila Limitada:** A estrutura `queue.Queue(maxsize=10)` atua como um *buffer* com capacidade estrita. O próprio gerenciamento da fila lida com estados de contenção equivalentes a variáveis de condição (*empty* e *full*): se a fila encher, os produtores são suspensos temporariamente; se esvaziar, os consumidores aguardam novas requisições.
*   **Encerramento Gracioso (Poison Pill):** Diferente da interrupção abrupta por *timeout*, este contexto introduz o uso de sinais de parada (conhecido como *Poison Pill* ou *Sentinel Value*, usando o valor `None`). Isso garante que os consumidores sejam encerrados de forma segura e sincronizada apenas quando todos os produtores terminarem de submeter o lote de perguntas.
*   **Exclusão Mútua Contínua:** Os *locks* (`mutex_cache` e `mutex_log`) continuam atuando para evitar condições de corrida na escrita do *cache* de respostas e na formatação das saídas de *log*.

### Como executar

Execute o *script* correspondente ao Contexto 3:

```bash
python3 serverC3.py
```
**Resultados esperados:**

O terminal e o arquivo ``execucao.log`` exibirão as ações intercaladas: você verá produtores diferentes enviando dados e consumidores os processando em paralelo, evidenciando o uso de múltiplas CPUs.

A aplicação será encerrada de forma limpa, confirmada pela mensagem "Recebeu sinal de encerramento" impressa por cada thread consumidora. Isso comprova a eficácia da sincronização no combate a falhas como inanição (starvation) ou processos zumbis aguardando eternamente por recursos.

## Contexto 4: C4 - Cache Compartilhado e Exclusão Mútua

O **Contexto 4** introduz uma estrutura de *cache* em memória acessível por todos os trabalhadores concorrentes. O objetivo deste cenário experimental é avaliar a eficácia do *cache* ao lidar com consultas repetidas e garantir que o compartilhamento dessa estrutura de dados não resulte em condições de corrida (*race conditions*).

### Como funciona
*   **Consultas Repetidas:** A fila de requisições é alimentada intencionalmente com consultas distintas seguidas de suas cópias exatas. Isso serve para forçar o sistema a registrar tanto "faltas" (*misses*) na primeira leitura quanto "acertos" (*hits*) nas leituras subsequentes.
*   **Economia de Processamento:** Quando ocorre um *hit*, a *thread* consumidora resgata a resposta diretamente da RAM, desviando completamente da busca no banco de dados SQLite e, mais importante, da custosa inferência de *tokens* pelo modelo local Ollama.
*   **Proteção de Área Crítica:** A estrutura do dicionário `cache_compartilhado` é uma área crítica. Para evitar que duas *threads* gravem ou leiam dados corrompidos ao mesmo tempo (o que causaria falhas no Python), o bloco de código que manipula o *cache* é protegido rigorosamente pelo `mutex_cache` (*Lock*).

### Como executar

Execute o *script* correspondente ao Contexto 4:

```bash
python3 serverC4.py
```
**Resultados esperados:**

Os dados de log serão gravados no arquivo execucao_c4.log.

Para as primeiras três perguntas, o terminal exibirá "FALTA NO CACHE (Miss)", e o tempo de conclusão será de vários segundos, pois a requisição precisou transitar pelo modelo de IA.

Para as últimas três perguntas, o terminal registrará "ACERTO NO CACHE (Hit)". O tempo de conclusão exibido saltará de vários segundos para praticamente zero (0.00s), demonstrando de forma contundente o tempo economizado e a redução da latência da aplicação.
