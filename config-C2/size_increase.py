# tamanho alvo: 2.5 Gigabyte
tamanho_alvo_bytes = 2.5 * 1024 * 1024 * 1024  
arquivo_original = "corpus_padrao.txt"
arquivo_gigante = "corpus_exagerado.txt"

print(f"Lendo '{arquivo_original}' e iniciando a multiplicação...")

with open(arquivo_original, 'r', encoding='utf-8') as f:
    texto = f.read()

with open(arquivo_gigante, 'w', encoding='utf-8') as f:
    # escreve o texto repetidas vezes até atingir o tamanho alvo (2.5 GB)
    while f.tell() < tamanho_alvo_bytes:
        f.write(texto)

print(f"O arquivo '{arquivo_gigante}' de 2.5 GB foi criado")
