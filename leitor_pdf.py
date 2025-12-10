import pdfplumber
import pandas as pd
import streamlit as st
import re
import unicodedata

def remover_acentos(texto):
    """Remove acentos e coloca em maiúsculo e remove quebras de linha"""
    try:
        if not texto: return ""
        # Remove quebras de linha para facilitar regex
        texto = str(texto).replace('\n', ' ').replace('\r', '')
        # Normaliza
        nfkd = unicodedata.normalize('NFD', texto)
        sem_acento = "".join([c for c in nfkd if not unicodedata.category(c) == 'Mn'])
        # Remove espaços duplos
        return re.sub(r'\s+', ' ', sem_acento.upper()).strip()
    except:
        return str(texto).upper()

def limpar_dinheiro_inteligente(valor_str):
    """
    Converte string de dinheiro para float detectando automaticamente o formato (BR ou US).
    """
    if not valor_str: return 0.0
    
    v = valor_str.replace('R$', '').strip()
    
    last_comma = v.rfind(',')
    last_dot = v.rfind('.')
    
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot: # BR 1.000,00
            v = v.replace('.', '').replace(',', '.')
        else: # US 1,000.00
            v = v.replace(',', '')
    elif last_dot != -1: # 1000.00
        if len(v) - last_dot - 1 == 3: v = v.replace('.', '')
    elif last_comma != -1: # 1000,00
        if len(v) - last_comma - 1 == 3: v = v.replace(',', '')
        else: v = v.replace(',', '.')

    try:
        return float(v)
    except:
        return 0.0

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF com Estratégia Dupla: Tabela Fundida ou Texto Corrido.
    Focado no padrão: Data ... 355 ... Valor ... Cargo
    """
    dados_encontrados = []
    
    # Regex Poderoso: Pega Data, Valor e o resto (Cargo)
    # Ex: 05/2018 ... 355 ... 4,341.94 ... ALUNO CFO
    regex_padrao = re.compile(r'(\d{2}/\d{4}).*?\b355\b.*?([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})(.*)')

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                
                # --- ESTRATÉGIA A: TABELAS (Ideal para quando o PDF é bem estruturado) ---
                tabelas = page.extract_tables()
                
                for tabela in tabelas:
                    if not tabela: continue
                    
                    # Procura coluna fundida (Tudo numa célula só)
                    idx_coluna_fundida = -1
                    
                    # Acha cabeçalho
                    for i, row in enumerate(tabela):
                        # Junta todo o texto da linha para procurar palavras chaves
                        linha_str = " ".join([remover_acentos(c) for c in row if c])
                        
                        if "DIREITO" in linha_str and "RUBR" in linha_str and "VALOR" in linha_str:
                            # Descobre qual índice tem o texto longo
                            for j, cell in enumerate(row):
                                c_text = remover_acentos(cell)
                                if "DIREITO" in c_text and "VALOR" in c_text:
                                    idx_coluna_fundida = j
                                    break
                            break
                    
                    # Se achou coluna fundida, processa
                    if idx_coluna_fundida != -1:
                        for row in tabela:
                            if len(row) <= idx_coluna_fundida: continue
                            
                            # Limpa muito bem a célula (tira \n, espaços)
                            texto_celula = remover_acentos(row[idx_coluna_fundida])
                            
                            match = regex_padrao.search(texto_celula)
                            if match:
                                val = limpar_dinheiro_inteligente(match.group(2))
                                if val > 0:
                                    # Limpa o cargo (remove numeros do codigo)
                                    cargo = re.sub(r'\d+', '', match.group(3)).strip()
                                    
                                    dados_encontrados.append({
                                        'Competencia': match.group(1),
                                        'Valor_Achado': val,
                                        'Cargo_Detectado': cargo
                                    })
                                    continue # Achou, vai pra proxima linha

                # --- ESTRATÉGIA B: TEXTO CORRIDO (Salva-vidas se a tabela falhar) ---
                # Se não achou nada na tabela, tenta ler o texto da página linha a linha
                texto_pagina = page.extract_text()
                if texto_pagina:
                    for linha in texto_pagina.split('\n'):
                        linha_limpa = remover_acentos(linha)
                        
                        # Filtra linhas de interesse
                        if "355" in linha_limpa and ("SUBSIDIO" in linha_limpa or "VANTAGEM" in linha_limpa):
                            match = regex_padrao.search(linha_limpa)
                            if match:
                                # Verifica se não é duplicata (mesmo mês já pego na tabela)
                                data_atual = match.group(1)
                                if not any(d['Competencia'] == data_atual for d in dados_encontrados):
                                    val = limpar_dinheiro_inteligente(match.group(2))
                                    if val > 0:
                                        cargo = re.sub(r'\d+', '', match.group(3)).strip()
                                        dados_encontrados.append({
                                            'Competencia': data_atual,
                                            'Valor_Achado': val,
                                            'Cargo_Detectado': cargo
                                        })

        # --- CONSOLIDAÇÃO ---
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            df['Competencia'] = pd.to_datetime(df['Competencia'], format='%m/%Y', dayfirst=True, errors='coerce')
            
            # Soma valores de mesma competência
            df = df.groupby('Competencia', as_index=False).agg({
                'Valor_Achado': 'sum',
                'Cargo_Detectado': 'first'
            })
            return df.sort_values('Competencia')
        else:
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return pd.DataFrame()
