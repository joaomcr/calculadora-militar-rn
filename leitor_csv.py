import pandas as pd
import streamlit as st

def extrair_dados_csv(arquivo_csv):
    """
    Lê um arquivo CSV padronizado (Modelo Manual) com as colunas:
    Competencia; Valor; Cargo
    """
    try:
        # Lê o CSV usando ponto e vírgula como separador (Padrão Excel Brasil)
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        
        # Limpa nomes das colunas (remove espaços extras)
        df.columns = df.columns.str.strip().str.lower()
        
        # Verifica se as colunas obrigatórias existem
        colunas_necessarias = ['competencia', 'valor', 'cargo']
        if not all(col in df.columns for col in colunas_necessarias):
            st.error("O arquivo CSV precisa ter as colunas: 'Competencia', 'Valor' e 'Cargo'.")
            return pd.DataFrame()

        dados_formatados = []

        for index, row in df.iterrows():
            data_str = str(row['competencia']).strip()
            valor_str = str(row['valor']).strip()
            cargo_str = str(row['cargo']).strip().upper()
            
            # Pula linhas vazias
            if not data_str or not valor_str:
                continue

            # Tratamento do Valor (Aceita 1000,00 ou 1000.00)
            valor_str = valor_str.replace('R$', '').replace(' ', '')
            if ',' in valor_str:
                valor_str = valor_str.replace('.', '').replace(',', '.')
            
            try:
                val_final = float(valor_str)
                
                # Só adiciona se tiver valor
                if val_final > 0:
                    dados_formatados.append({
                        'Competencia': data_str,
                        'Valor_Achado': val_final,
                        'Cargo_Detectado': cargo_str
                    })
            except:
                continue # Pula linha com valor inválido

        # Consolidação Final
        if dados_formatados:
            df_final = pd.DataFrame(dados_formatados)
            # Converte data (espera formato DD/MM/AAAA ou MM/AAAA)
            df_final['Competencia'] = pd.to_datetime(df_final['Competencia'], dayfirst=True, errors='coerce')
            
            # Remove datas inválidas (NaT)
            df_final = df_final.dropna(subset=['Competencia'])
            
            # Soma valores de mesma competência
            df_final = df_final.groupby('Competencia', as_index=False).agg({
                'Valor_Achado': 'sum',
                'Cargo_Detectado': 'first'
            })
            
            return df_final.sort_values('Competencia')
        
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao ler CSV: {e}")
        return pd.DataFrame()
