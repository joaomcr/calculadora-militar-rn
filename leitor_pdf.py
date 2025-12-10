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

def limpar_dinheiro_inteligente(valor_str):
    """
    Converte string de dinheiro para float detectando automaticamente o formato (BR ou US).
    Usa a lógica do 'último separador' para decidir qual é o decimal.
    """
    if not valor_str: return 0.0
    
    # Limpa sujeira básica
    v = valor_str.replace('R$', '').replace(' ', '').strip()
    
    # Encontra posições dos separadores
    last_comma = v.rfind(',')
    last_dot = v.rfind('.')
    
    # Cenário 1: Não tem separadores (ex: "1000")
    if last_comma == -1 and last_dot == -1:
        pass # Já está pronto para converter

    # Cenário 2: Tem vírgula e ponto (ex: "1.000,00" ou "1,000.00")
    elif last_comma != -1 and last_dot != -1:
        if last_comma > last_dot: # Formato BR (1.000,00)
            v = v.replace('.', '').replace(',', '.')
        else: # Formato US (1,000.00)
            v = v.replace(',', '')

    # Cenário 3: Só tem ponto (ex: "1000.00" ou "1.000")
    elif last_dot != -1:
        # Se tem 3 casas decimais (ex: 1.000), assumimos que é milhar BR
        if len(v) - last_dot - 1 == 3:
             v = v.replace('.', '')
        # Caso contrário (ex: 1000.00 ou 10.00), assumimos decimal
        else:
             pass # Python entende ponto como decimal nativamente

    # Cenário 4: Só tem vírgula (ex: "1000,00" ou "1,000")
    elif last_comma != -1:
        # Se tem 3 casas (ex: 1,000), assumimos milhar US
        if len(v) - last_comma - 1 == 3:
             v = v.replace(',', '')
        # Caso contrário (ex: 1000,50), assumimos decimal BR
        else:
             v = v.replace(',', '.')

    try:
        return float(v)
    except:
        return 0.0

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF e extrai dados tabulares.
    Suporta colunas fundidas e formatos variados de moeda.
    """
    dados_encontrados = []
    
    # Regex Simplificado: Foca em achar Data, 355 e Valor.
    # O resto (cargo) pegamos de forma mais solta no final.
    # Ex: "05/2018 ... 355 ... 4,341.94 ..."
    regex_linha_fundida = re.compile(r'(\d{2}/\d{4}).*?\b355\b.*?([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})(.*)')

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
                        
                        tem_direito = any("DIREITO" in cell for cell in row_text) or any("COMPET" in cell for cell in row_text)
                        
                        if tem_direito:
                            header_row = i
                            
                            # 1. Tenta mapear colunas separadas
                            for j, cell in enumerate(row_text):
                                if "DIREITO" in cell or "COMPET" in cell: idx_competencia = j
                                elif "RUBR" in cell or "CODIGO" in cell: idx_rubrica = j
                                elif "VALOR" in cell or "RENDIMENTO" in cell: idx_valor = j
                                elif "CARGO" in cell or "FUNCAO" in cell or "POSTO" in cell: idx_cargo = j
                            
                            # 2. Tenta detectar COLUNA FUNDIDA
                            for j, cell in enumerate(row_text):
                                if "DIREITO" in cell and "RUBR" in cell and "VALOR" in cell:
                                    idx_coluna_fundida = j
                                    break
                            break
                    
                    if header_row == -1: continue

                    # --- B. EXTRAIR DADOS ---
                    for row in tabela[header_row+1:]:
                        try:
                            # MODALIDADE 1: COLUNA FUNDIDA
                            if idx_coluna_fundida != -1:
                                if len(row) <= idx_coluna_fundida: continue
                                
                                texto_celula = str(row[idx_coluna_fundida]).replace('\n', ' ').strip()
                                
                                match = regex_linha_fundida.search(texto_celula)
                                if match:
                                    data_final = match.group(1)
                                    val_final = limpar_dinheiro_inteligente(match.group(2))
                                    
                                    # Tenta limpar o cargo do resto da string
                                    resto = match.group(3)
                                    # Remove números soltos (código do cargo) e caracteres estranhos
                                    cargo_sujo = re.sub(r'\d+', '', resto) 
                                    cargo_final = remover_acentos(cargo_sujo).strip()
                                    
                                    if val_final > 0:
                                        dados_encontrados.append({
                                            'Competencia': data_final,
                                            'Valor_Achado': val_final,
                                            'Cargo_Detectado': cargo_final
                                        })
                            
                            # MODALIDADE 2: COLUNAS SEPARADAS
                            elif idx_competencia != -1 and idx_valor != -1:
                                if len(row) <= max(idx_competencia, idx_rubrica, idx_valor): continue
                                
                                raw_rubrica = str(row[idx_rubrica]) if idx_rubrica != -1 and row[idx_rubrica] else ""
                                
                                if "355" in raw_rubrica:
                                    raw_data = row[idx_competencia]
                                    raw_valor = row[idx_valor]
                                    raw_cargo = row[idx_cargo] if idx_cargo != -1 else ""
                                    
                                    match_data = re.search(r'(\d{2}/\d{4})', str(raw_data))
                                    if not match_data: continue
                                    
                                    val_final = limpar_dinheiro_inteligente(str(raw_valor))
                                    
                                    if val_final > 0:
                                        dados_encontrados.append({
                                            'Competencia': match_data.group(1),
                                            'Valor_Achado': val_final,
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
