import pdfplumber
import pandas as pd
import streamlit as st
import re

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF e extrai dados tabulares focando nas colunas especificadas:
    - Competência: 'Mês/Ano Direito'
    - Rubrica: 'Rubr'
    - Valor: 'Valor'
    - Cargo: 'Descrição do Cargo'
    """
    dados_encontrados = []
    
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                # 1. Tenta extrair tabelas estruturadas
                tabelas = page.extract_tables()
                
                for tabela in tabelas:
                    if not tabela: continue
                    
                    # Variáveis de índice das colunas
                    idx_competencia = -1
                    idx_rubrica = -1
                    idx_valor = -1
                    idx_cargo = -1
                    
                    header_row = -1
                    
                    # --- A. ENCONTRAR O CABEÇALHO ---
                    for i, row in enumerate(tabela):
                        # Limpa e normaliza o texto da linha para busca
                        row_text = [str(cell).strip().upper() if cell else "" for cell in row]
                        
                        # Verifica se é a linha de cabeçalho baseada nos nomes que você passou
                        # Usamos palavras-chave parciais para garantir (ex: "DIREITO" pega "Mês/Ano Direito")
                        tem_direito = any("DIREITO" in cell for cell in row_text) or any("COMPET" in cell for cell in row_text)
                        tem_rubr = any("RUBR" in cell for cell in row_text) or any("CÓDIGO" in cell for cell in row_text)
                        tem_valor = any("VALOR" in cell for cell in row_text) or any("RENDIMENTO" in cell for cell in row_text)
                        
                        if tem_direito and (tem_rubr or tem_valor):
                            header_row = i
                            # Mapeia os índices exatos
                            for j, cell in enumerate(row_text):
                                if "DIREITO" in cell or "COMPET" in cell: idx_competencia = j
                                elif "RUBR" in cell or "CODIGO" in cell: idx_rubrica = j
                                elif "VALOR" in cell or "RENDIMENTO" in cell: idx_valor = j
                                elif "CARGO" in cell or "FUNÇÃO" in cell or "DESCRIÇÃO" in cell: idx_cargo = j
                            break
                    
                    # Se não achou cabeçalho nesta tabela, pula para a próxima
                    if header_row == -1:
                        continue
                        
                    # --- B. EXTRAIR DADOS ---
                    # Começa a ler da linha seguinte ao cabeçalho
                    for row in tabela[header_row+1:]:
                        # Verifica se a linha tem tamanho suficiente
                        if len(row) <= max(idx_competencia, idx_rubrica, idx_valor):
                            continue
                            
                        # Extrai Rubrica
                        raw_rubrica = str(row[idx_rubrica]) if idx_rubrica != -1 and row[idx_rubrica] else ""
                        
                        # FILTRO: Só queremos a Rubrica 355
                        if "355" in raw_rubrica:
                            raw_data = row[idx_competencia] if idx_competencia != -1 else ""
                            raw_valor = row[idx_valor] if idx_valor != -1 else ""
                            raw_cargo = row[idx_cargo] if idx_cargo != -1 else ""
                            
                            # Limpeza e Validação
                            try:
                                # 1. Data (MM/AAAA)
                                match_data = re.search(r'(\d{2}/\d{4})', str(raw_data))
                                if not match_data: continue
                                data_final = match_data.group(1)
                                
                                # 2. Valor (R$ X.XXX,XX)
                                val_str = str(raw_valor).replace('R$', '').replace('.', '').replace(',', '.').strip()
                                val_final = float(val_str)
                                
                                # 3. Cargo
                                cargo_final = str(raw_cargo).strip().upper()
                                
                                dados_encontrados.append({
                                    'Competencia': data_final,
                                    'Valor_Achado': val_final,
                                    'Cargo_Detectado': cargo_final
                                })
                            except:
                                continue

        # --- C. CONSOLIDAÇÃO ---
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            df['Competencia'] = pd.to_datetime(df['Competencia'], format='%m/%Y', dayfirst=True, errors='coerce')
            
            # Soma valores de mesma competência e mantém o cargo
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
