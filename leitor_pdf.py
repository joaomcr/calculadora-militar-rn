import pdfplumber
import re
import pandas as pd
import streamlit as st

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF do Portal do Servidor RN e extrai (Data, Valor).
    Filtra pela Rubrica 355 (Subsídio) ou pela palavra chave.
    """
    dados_encontrados = []
    
    # 1. Regex para Data (MM/AAAA)
    regex_data = re.compile(r'(\d{2}/\d{4})') 
    
    # 2. Regex para Dinheiro (Captura o que vem depois de R$)
    # Nota: No seu PDF o R$ tem um espaço depois. Ex: "R$ 6.112,02"
    regex_valor = re.compile(r'R\$\s+(\d{1,3}(?:\.\d{3})*,\d{2})')

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            if not pdf.pages:
                return pd.DataFrame()

            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                for linha in text.split('\n'):
                    
                    # --- FILTRO HÍBRIDO (RUBRICA 355 + PALAVRA CHAVE) ---
                    # Verifica se é uma linha de Vantagem (Crédito)
                    eh_vantagem = "Vantagem" in linha
                    
                    # Verifica se é o código 355 ou a palavra SUBSIDIO
                    # Colocamos espaços em volta do " 355 " para não confundir com R$ 355,00
                    tem_rubrica = " 355 " in linha
                    tem_palavra = "SUBSIDIO" in linha or "SUBSÍDIO" in linha
                    
                    # A Lógica: Tem que ser Vantagem E (Ter o código OU a palavra)
                    if eh_vantagem and (tem_rubrica or tem_palavra):
                        
                        match_data = regex_data.search(linha)
                        match_valor = regex_valor.search(linha)
                        
                        if match_data and match_valor:
                            data_str = match_data.group(1)
                            valor_str = match_valor.group(1)
                            
                            try:
                                # Limpa o valor para virar número float
                                valor_limpo = float(valor_str.replace('.', '').replace(',', '.'))
                                
                                dados_encontrados.append({
                                    'Competencia': data_str,
                                    'Valor_Achado': valor_limpo
                                })
                            except:
                                continue

        # Consolidação
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            df['Competencia'] = pd.to_datetime(df['Competencia'], format='%m/%Y', dayfirst=True, errors='coerce')
            
            # Soma valores se houver duplicidade no mesmo mês
            df = df.groupby('Competencia', as_index=False)['Valor_Achado'].sum()
            
            return df
        else:
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro na leitura do PDF: {e}")
        return pd.DataFrame()