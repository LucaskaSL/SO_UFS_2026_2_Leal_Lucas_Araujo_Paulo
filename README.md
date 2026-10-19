# SO_UFS_2026_2_Leal_Lucas_Araujo_Paulo

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
