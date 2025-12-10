import pdfplumber
import pandas as pd
import streamlit as st
import re
import unicodedata

def remover_acentos(texto):
    """Remove acentos e coloca em maiúsculo (Ex: 'Descrição' -> 'DESCRICAO')"""
    try:
        if not texto: return ""
        nfkd = unicodedata.normalize('NFD', str(texto))
        sem_acento = "".join([c for c in nfkd if not unicodedata.category(c) == 'Mn'])
        return sem_acento.upper()
    except:
        return str(texto).upper()

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF e extrai dados tabulares.
    Detecta automaticamente se as colunas estão separadas ou fundidas (comum em alguns PDFs).
    """
    dados_encontrados = []
    
    # Regex para o caso de Coluna Fundida (Tudo junto)
    # Ex: "05/2018 Vantag 355 SUBSIDIO... 4,341.94 106108 ALUNO CFO..."
    # Grupo 1: Data | Grupo 2: Valor | Grupo 3: Cargo
    regex_linha_fundida = re.compile(r'(\d{2}/\d{4}).*?\s355\s.*?\s([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+\d+\s+(.*)')

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                tabelas = page.extract_tables()
                
                for tabela in tabelas:
                    if not tabela: continue
                    
                    idx_competencia = -1
                    idx_rubrica = -1
                    idx_valor = -1
                    idx_cargo = -1
                    idx_coluna_fundida = -1
                    
                    header_row = -1
                    
                    # --- A. ENCONTRAR O CABEÇALHO ---
                    for i, row in enumerate(tabela):
                        row_text = [remover_acentos(cell) if cell else "" for cell in row]
                        
                        # Verifica palavras-chave
                        tem_direito = any("DIREITO" in cell for cell in row_text) or any("COMPET" in cell for cell in row_text)
                        tem_rubr = any("RUBR" in cell for cell in row_text)
                        tem_valor = any("VALOR" in cell for cell in row_text)
                        
                        if tem_direito:
                            header_row = i
                            
                            # Tenta mapear colunas separadas
                            for j, cell in enumerate(row_text):
                                if "DIREITO" in cell or "COMPET" in cell: idx_competencia = j
                                elif "RUBR" in cell or "CODIGO" in cell: idx_rubrica = j
                                elif "VALOR" in cell or "RENDIMENTO" in cell: idx_valor = j
                                elif "CARGO" in cell or "FUNCAO" in cell or "POSTO" in cell: idx_cargo = j
                            
                            # Tenta detectar COLUNA FUNDIDA (Caso do seu PDF)
                            # Se "DIREITO", "RUBR" e "VALOR" estiverem na MESMA célula
                            for j, cell in enumerate(row_text):
                                if "DIREITO" in cell and "RUBR" in cell and "VALOR" in cell:
                                    idx_coluna_fundida = j
                                    break
                            
                            break
                    
                    if header_row == -1: continue

                    # --- B. EXTRAIR DADOS ---
                    for row in tabela[header_row+1:]:
                        try:
                            # MODALIDADE 1: COLUNA FUNDIDA (Seu PDF atual)
                            if idx_coluna_fundida != -1:
                                if len(row) <= idx_coluna_fundida: continue
                                
                                texto_celula = str(row[idx_coluna_fundida]).replace('\n', ' ')
                                
                                # Aplica o Regex para separar o texto
                                match = regex_linha_fundida.search(texto_celula)
                                if match:
                                    data_final = match.group(1)
                                    val_str = match.group(2).replace('.', '').replace(',', '.')
                                    val_final = float(val_str)
                                    cargo_final = remover_acentos(match.group(3)).strip()
                                    
                                    dados_encontrados.append({
                                        'Competencia': data_final,
                                        'Valor_Achado': val_final,
                                        'Cargo_Detectado': cargo_final
                                    })
                            
                            # MODALIDADE 2: COLUNAS SEPARADAS (Padrão)
                            elif idx_competencia != -1 and idx_valor != -1:
                                if len(row) <= max(idx_competencia, idx_rubrica, idx_valor): continue
                                
                                raw_rubrica = str(row[idx_rubrica]) if idx_rubrica != -1 and row[idx_rubrica] else ""
                                
                                if "355" in raw_rubrica:
                                    raw_data = row[idx_competencia]
                                    raw_valor = row[idx_valor]
                                    raw_cargo = row[idx_cargo] if idx_cargo != -1 else ""
                                    
                                    match_data = re.search(r'(\d{2}/\d{4})', str(raw_data))
                                    if not match_data: continue
                                    
                                    val_str = str(raw_valor).replace('R$', '').replace('.', '').replace(',', '.').strip()
                                    
                                    dados_encontrados.append({
                                        'Competencia': match_data.group(1),
                                        'Valor_Achado': float(val_str),
                                        'Cargo_Detectado': remover_acentos(raw_cargo).strip()
                                    })
                        except:
                            continue

        # --- C. CONSOLIDAÇÃO ---
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            df['Competencia'] = pd.to_datetime(df['Competencia'], format='%m/%Y', dayfirst=True, errors='coerce')
            
            # Soma valores e pega o primeiro cargo válido
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



