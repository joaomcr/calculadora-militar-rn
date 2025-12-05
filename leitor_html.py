from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import re
import unicodedata

def remover_acentos(texto):
    """Remove acentos e coloca em maiúsculo (Ex: 'Subsídio' -> 'SUBSIDIO')"""
    try:
        if not texto: return ""
        nfkd = unicodedata.normalize('NFD', str(texto))
        sem_acento = "".join([c for c in nfkd if not unicodedata.category(c) == 'Mn'])
        return sem_acento.upper()
    except:
        return str(texto).upper()

def extrair_dados_html(conteudo_html):
    """
    Lê HTML e extrai: Competência, Valor e CARGO.
    Versão Flexível: Normaliza acentos e busca termos parciais.
    """
    dados_encontrados = []
    
    try:
        soup = BeautifulSoup(conteudo_html, 'html.parser')
        tabelas = soup.find_all('table')
        
        if not tabelas: return pd.DataFrame()

        for tabela in tabelas:
            linhas = tabela.find_all('tr')
            if not linhas: continue
                
            # --- 1. MAPEAMENTO DE COLUNAS ---
            idx_competencia = -1
            idx_valor = -1
            idx_cargo = -1
            idx_rubrica = -1
            
            # Tenta identificar pelo cabeçalho
            cabecalho = linhas[0].find_all(['th', 'td'])
            if cabecalho:
                # Normaliza o cabeçalho (remove acentos)
                textos_cabecalho = [remover_acentos(col.get_text(strip=True)) for col in cabecalho]
                
                for i, texto in enumerate(textos_cabecalho):
                    # Competência
                    if "DIREITO" in texto or "COMPET" in texto or "REFER" in texto: 
                        idx_competencia = i
                    # Valor
                    elif "VALOR" in texto or "RENDIMENTO" in texto or "LIQUIDO" in texto: 
                        idx_valor = i
                    # Rubrica
                    elif "RUBR" in texto or "CODIGO" in texto or "COD" in texto:
                        idx_rubrica = i
                    # Cargo
                    elif ("CARGO" in texto or "FUNCAO" in texto or "POSTO" in texto or 
                          "GRADUACAO" in texto or "DESCRICAO" in texto): 
                        idx_cargo = i

            # --- 2. VARREDURA DAS LINHAS ---
            inicio = 1 if cabecalho else 0
            
            for linha in linhas[inicio:]:
                colunas = linha.find_all('td')
                if not colunas: continue
                
                # Texto da linha normalizado (sem acentos)
                texto_linha = remover_acentos(linha.get_text(" ", strip=True))
                
                # --- LÓGICA DE FILTRO FLEXÍVEL ---
                eh_alvo = False
                
                # Estratégia A: Verifica coluna da Rubrica (Se mapeada)
                if idx_rubrica != -1 and len(colunas) > idx_rubrica:
                    codigo = remover_acentos(colunas[idx_rubrica].get_text(strip=True))
                    # Verifica se contém "355" (Ex: "00355", "355", "355-A")
                    if "355" in codigo:
                        eh_alvo = True
                
                # Estratégia B: Verifica célula exata (Se A falhou ou não tem coluna)
                if not eh_alvo:
                    for col in colunas:
                        if col.get_text(strip=True) == "355":
                            eh_alvo = True
                            break
                
                # Estratégia C: Busca no texto completo (Fallback)
                if not eh_alvo:
                    # Tem que ter "355" E ("SUBSID" ou "VANTAGEM") na mesma linha
                    # "SUBSID" pega SUBSIDIO, SUBSÍDIO, SUBSIDIAR...
                    tem_rubrica_txt = re.search(r'\b355\b', texto_linha)
                    tem_palavra_txt = "SUBSID" in texto_linha or "VANTAGEM" in texto_linha
                    
                    if tem_rubrica_txt and tem_palavra_txt:
                        eh_alvo = True

                # Se confirmou que é a linha certa, extrai os dados
                if eh_alvo:
                    # DATA
                    texto_data = ""
                    if idx_competencia != -1 and len(colunas) > idx_competencia:
                        texto_data = colunas[idx_competencia].get_text(strip=True)
                    else:
                        match = re.search(r'\d{2}/\d{4}', texto_linha)
                        if match: texto_data = match.group(0)

                    # VALOR
                    valor_final = 0.0
                    if idx_valor != -1 and len(colunas) > idx_valor:
                        valor_final = limpar_valor(colunas[idx_valor].get_text(strip=True))
                    else:
                        valor_final = achar_maior_valor_na_linha(colunas)
                    
                    # CARGO
                    texto_cargo = ""
                    if idx_cargo != -1 and len(colunas) > idx_cargo:
                        texto_cargo = remover_acentos(colunas[idx_cargo].get_text(strip=True))
                    
                    # Salva
                    if re.match(r'\d{2}/\d{4}', texto_data) and valor_final > 0:
                        dados_encontrados.append({
                            'Competencia': texto_data,
                            'Valor_Achado': valor_final,
                            'Cargo_Detectado': texto_cargo
                        })

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
        st.error(f"Erro ao ler HTML: {e}")
        return pd.DataFrame()

def limpar_valor(texto):
    try:
        # Remove tudo que não é numero ou virgula/ponto decimal
        v_limpo = remover_acentos(texto).replace('R$', '').replace('.', '').replace(' ', '')
        return float(v_limpo.replace(',', '.'))
    except:
        return 0.0

def achar_maior_valor_na_linha(colunas):
    maior = 0.0
    for col in colunas:
        val = limpar_valor(col.get_text(strip=True))
        if val > maior: 
            maior = val
    return maior