import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar

class CalculadoraMilitar:
    def __init__(self, data_ingresso, data_ajuizamento, historico_promocoes, datas_ferias_pdf=[]):
        # 1. Configurações
        self.data_ingresso = pd.to_datetime(data_ingresso, dayfirst=True)
        self.data_ajuizamento = pd.to_datetime(data_ajuizamento, dayfirst=True)
        self.data_corte_selic = pd.to_datetime('2021-12-01') # Marco da EC 113
        self.datas_ferias_pdf = pd.to_datetime(datas_ferias_pdf, dayfirst=True, errors='coerce')
        
        # Histórico (Ordenado)
        self.df_carreira = pd.DataFrame(historico_promocoes)
        self.df_carreira['Data'] = pd.to_datetime(self.df_carreira['Data'], dayfirst=True)
        self.df_carreira = self.df_carreira.sort_values('Data')

        try:
            # --- A. CARREGAMENTO DOS ÍNDICES (PRESERVADO) ---
            self.df_indices = pd.read_csv('dados/indices.csv', sep=';')
            self.df_indices.columns = self.df_indices.columns.str.strip()
            self.df_indices['Data'] = pd.to_datetime(self.df_indices['Data'], dayfirst=True, errors='coerce')
            
            # Limpeza Numérica Pesada (Remove %, R$, vírgulas)
            cols_financeiras = ['CorrecaoMonetaria', 'Selic', 'JurosPoupanca', 'SelicAcumulada'] 
            for col in cols_financeiras:
                if col in self.df_indices.columns:
                    self.df_indices[col] = self.df_indices[col].astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False)
                    self.df_indices[col] = pd.to_numeric(self.df_indices[col], errors='coerce').fillna(0.0)
            
            self.df_indices = self.df_indices.sort_values('Data')

            # Captura Numerador IPCA (Nov/21) - Lógica que bateu com Excel
            try:
                data_nov21 = pd.to_datetime('2021-11-01')
                self.indice_ref_nov21 = self.df_indices.loc[self.df_indices['Data'] == data_nov21, 'CorrecaoMonetaria'].values[0]
            except:
                self.indice_ref_nov21 = 1.0

            # --- B. CARREGAMENTO TABELA CORONEL (PRESERVADO) ---
            self.df_tabela_lei = pd.read_csv('dados/tabelas_lei.csv', sep=';')
            self.df_tabela_lei['Valor'] = self.df_tabela_lei['Valor'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            self.df_tabela_lei['Valor'] = pd.to_numeric(self.df_tabela_lei['Valor'])
            self.df_tabela_lei['Data_Inicio'] = pd.to_datetime(self.df_tabela_lei['Data_Inicio'], dayfirst=True)
            self.df_tabela_lei['Data_Fim'] = pd.to_datetime(self.df_tabela_lei['Data_Fim'], dayfirst=True)

            # --- C. CARREGAMENTO ESCALONAMENTO (PRESERVADO) ---
            df_esc = pd.read_csv('dados/escalonamento.csv', sep=';')
            df_esc['Percentual'] = df_esc['Percentual'].astype(str).str.replace(',', '.', regex=False)
            # Divide por 100 para usar como fator (Ex: 20 vira 0.20)
            df_esc['Percentual'] = pd.to_numeric(df_esc['Percentual']) / 100
            self.escalonamento = pd.Series(df_esc.Percentual.values, index=df_esc.Posto).to_dict()
            
        except Exception as e:
            print(f"ERRO CRÍTICO NO SETUP: {e}")
            self.df_indices = pd.DataFrame()
            self.df_tabela_lei = pd.DataFrame()
            self.escalonamento = {}

    # --- MÉTODOS AUXILIARES ---
    def gerar_timeline(self):
        # Data de Início (Prescrição 5 anos)
        marco_prescricional = self.data_ajuizamento - relativedelta(years=5)
        inicio = marco_prescricional.replace(day=1)
        if inicio < self.data_ingresso: inicio = self.data_ingresso.replace(day=1)
        
        # --- CORREÇÃO DA DATA FINAL (EXIGIBILIDADE) ---
        # Não podemos calcular o mês corrente pois o pagamento ainda não ocorreu.
        # Definimos o fim como o primeiro dia do MÊS ANTERIOR ao atual.
        # Ex: Se hoje é 04/12/2025, calculamos até 01/11/2025.
        data_hoje = datetime.today()
        fim = data_hoje.replace(day=1) - relativedelta(months=1)
        
        # Garante que não dê erro se a data final for menor que a inicial (recém ingressado)
        if fim < inicio:
            fim = inicio

        # 1. Gera meses normais (Dia 01)
        datas_normais = pd.date_range(start=inicio, end=fim, freq='MS')
        
        # 2. Gera datas de 13º Salário (Dia 13 de Dezembro de cada ano)
        # Pega todos os anos únicos da lista
        anos = datas_normais.year.unique()
        datas_13 = []

        for ano in anos:
            data_13 = pd.Timestamp(year=ano, month=12, day=13)
            # Só adiciona se o mês de dezembro já tiver passado ou estiver no range
            if data_13 <= fim:
                datas_13.append(data_13)
                
        # FÉRIAS (Dia 15) - Baseado no que veio do PDF
        datas_ferias = []
        for data_f in self.datas_ferias_pdf:
            # Só adiciona se a data do PDF estiver dentro da prescrição/processo
            if inicio <= data_f <= fim:
                # Garante que seja dia 15 para bater com o padrão
                data_virtual = data_f.replace(day=15)
                datas_ferias.append(data_virtual)

        # Junta tudo e ordena
        todas_datas = list(datas_normais) + datas_13 + datas_ferias
        todas_datas.sort()
        
        return pd.DataFrame({'Competencia': todas_datas})
    # Adicione este método auxiliar à classe CalculadoraMilitar

    def extrair_detalhes_laudo(self, df):
        """
        Extrai Nível e Tipo (Rubrica) com base na Competencia e Posto_Vigente, 
        preparando as colunas para o PDF.
        """
        
        def determinar_rubrica(row):
            """ 355-Subsídio, 351-13º, 359-Férias """
            if row['Competencia'].day == 13:
                return 'Grat. Natalina'
            elif row['Competencia'].day == 15:
                return 'Férias'
            return 'Subsídio'
 
        def determinar_nivel(row):
            posto = str(row['Posto_Vigente']).split('-')[-1].strip() # Pega só o posto se for 13º ou Férias
            data_ref = row['Competencia'].replace(day=1)
            
            if "ASPIRANTE" in posto.upper() or "ALUNO CFO" in posto.upper(): 
                # Se for ASP/Aluno, usamos a lógica do fator e mapeamos para Nível
                fator = self.get_fator_nivel(posto, data_ref)
                if fator >= (1.03 ** 2): return 'III'
                elif fator >= 1.03: return 'II'
                return 'I'
            
            # Para militares de carreira (Tempo de Serviço)
            ultimo_dia = data_ref + relativedelta(day=31)
            anos = relativedelta(ultimo_dia, self.data_ingresso).years
            trienios = int(anos / 3)
            
            # Mapeamento Nível
            if trienios >= 3: return 'IV' # 9+ anos
            if trienios == 2: return 'III' # 6-8 anos
            if trienios == 1: return 'II' # 3-5 anos
            return 'I' # 0-2 anos

        # 1. Cria a coluna 'Rubrica_Tipo' (Tipo)
        df['Rubrica_Tipo'] = df.apply(determinar_rubrica, axis=1)

        # 2. Cria a coluna 'Nivel'
        df['Nivel'] = df.apply(determinar_nivel, axis=1)
        
        # 3. Renomeia Posto (Posto/Grad) e ajusta o nome no 13º/Férias
        def formatar_posto_grad(posto_vigente):
            posto_str = str(posto_vigente).strip()
        
            # 1. TRATAMENTO DE TRANSIÇÃO (Setas)
            # Ex: "Aluno CFO 3 (24d) -> Aspirante (7d)"
            if ' -> ' in posto_str:
                return posto_str.replace(' -> ', ' / \n')
            
            # 2. TRATAMENTO DE RUBRICA (13º/Férias)
            # Ex: "13º Salário - Aluno CFO 3"
            if ' - ' in posto_str:
            # Pega apenas o que vem depois do PRIMEIRO " - "
            # O .split(' - ', 1)[-1] garante que só pegamos o último pedaço
                return posto_str.split(' - ', 1)[-1].strip()

            # 3. VALOR PADRÃO (Posto único)
            # Ex: "Aluno CFO 3"
            return posto_str 
        df['Posto_Grad'] = df['Posto_Vigente'].apply(formatar_posto_grad)
        return df

    
    #def gerar_tabela_base(self):
        # Gera timeline com meses normais E 13º
        #df = self.gerar_timeline()
        
        # O resto da lógica funciona igual, pois buscar_posto e buscar_valor
        # funcionam baseados em data <= data_atual, então dia 13 pega o posto de dez.
        
        # Lógica Pro Rata (Mantida)
        #resultado_nominal = df.apply(self.calcular_valor_nominal_com_prorata, axis=1)
        #df['Posto_Vigente'] = resultado_nominal[0]
        #df['Valor_Devido'] = resultado_nominal[1]
        
        #df['Norma_Legal'] = df['Competencia'].apply(self.buscar_norma_vigente)
        
        # Identificação visual do 13º
        # Se for dia 13, muda o nome do posto para "13º Salário - [Posto]"
        #mask_13 = df['Competencia'].dt.day == 13
        #df.loc[mask_13, 'Posto_Vigente'] = "13º Salário - " + df.loc[mask_13, 'Posto_Vigente']
        
        #df['Valor_Pago'] = 0.0 
        #return df


    def buscar_posto_na_data(self, data_especifica):
        """ Retorna o posto vigente em um dia específico (Para usar no Pro Rata) """
        promocoes = self.df_carreira[self.df_carreira['Data'] <= data_especifica]
        if promocoes.empty: return "Não Ingressou"
        return promocoes.iloc[-1]['Posto']

    def buscar_valor_coronel(self, data_competencia):
        filtro = (self.df_tabela_lei['Data_Inicio'] <= data_competencia) & \
                 (self.df_tabela_lei['Data_Fim'] >= data_competencia)
        res = self.df_tabela_lei[filtro]
        if res.empty: return 0.0
        return float(res.iloc[0]['Valor'])

    def get_fator_nivel(self, posto, data_referencia):
        """ 
        Calcula o multiplicador do Nível.
        CORREÇÃO: Agora usa Juros Compostos (Progressão sobre nível anterior).
        Fórmula: 1.03 elevado ao número de triênios.
        """
        posto = str(posto).upper().strip()
        if posto == "NÃO INGRESSOU": return 1.0
        
        # --- REGRAS DE EXCEÇÃO (BOLSAS) ---
        # Nível I (0 triênios) = 1.03^0 = 1.00
        # Nível II (1 triênio) = 1.03^1 = 1.03
        # Nível III (2 triênios) = 1.03^2 = 1.0609
        
        if "ASPIRANTE" in posto or "ASP." in posto: return 1.00
        if "ALUNO CFO" in posto:
            if "3" in posto or "III" in posto: return 1.03 ** 2 # Nível III
            elif "2" in posto or "II" in posto: return 1.03 ** 2 # Nível III
            elif "1" in posto or posto.endswith(" I"): return 1.03 ** 1 # Nível II
            return 1.03 ** 1 # Padrão

        # --- REGRA GERAL (TEMPO DE SERVIÇO) ---
        ultimo_dia = data_referencia + relativedelta(day=31)
        anos = relativedelta(ultimo_dia, self.data_ingresso).years
        trienios = int(anos / 3)
        
        # AQUI ESTÁ A CORREÇÃO MATEMÁTICA:
        # Antes: 1 + (trienios * 0.03) -> Juros Simples
        # Agora: 1.03 ** trienios      -> Juros Compostos (Sobre o anterior)
        return 1.03 ** trienios

    # --- NOVO: LÓGICA PRO RATA DIE ---
    def calcular_valor_nominal_com_prorata(self, row):
        """
        Calcula o valor devido no mês. 
        Trata:
        1. Férias (Dia 15)
        2. 13º Salário (Dia 13)
        3. Mês Normal com ou sem Promoção (Dia 01)
        """
        
        # --- CORREÇÃO DO ERRO AQUI ---
        # Definimos data_atual logo no início extraindo da linha
        data_atual = row['Competencia'] 
        
        # 1. LÓGICA DE FÉRIAS (DIA 15)
        if data_atual.day == 15:
            # Para saber o valor, olhamos para o dia 01 do mesmo mês
            data_ref = data_atual.replace(day=1)
            
            posto = self.buscar_posto_na_data(data_ref)
            base = self.buscar_valor_coronel(data_ref)
            perc = self.escalonamento.get(posto, 0.0)
            nivel = self.get_fator_nivel(posto, data_ref)
            
            valor_cheio = base * perc * nivel
            
            # Férias é 1/3 do valor cheio
            return pd.Series([f"Férias (1/3) - {posto}", valor_cheio / 3])

        # 2. LÓGICA DE 13º SALÁRIO (DIA 13)
        elif data_atual.day == 13:
            # Pega referência de dezembro (dia 01)
            data_ref = data_atual.replace(day=1)
            
            posto = self.buscar_posto_na_data(data_ref)
            base = self.buscar_valor_coronel(data_ref)
            perc = self.escalonamento.get(posto, 0.0)
            nivel = self.get_fator_nivel(posto, data_ref)
            
            valor_cheio = base * perc * nivel
            
            return pd.Series([f"13º Salário - {posto}", valor_cheio])

        # 3. LÓGICA MENSAL COMUM (DIA 01 - PRO RATA)
        else:
            data_inicio_mes = data_atual # Mantém nome antigo para a lógica abaixo
            
            # Descobre o último dia do mês (28, 29, 30 ou 31)
            ultimo_dia_numero = calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1]
            data_fim_mes = data_inicio_mes.replace(day=ultimo_dia_numero)
            
            # Verifica promoção DENTRO deste mês
            promocao_no_mes = self.df_carreira[
                (self.df_carreira['Data'] > data_inicio_mes) & 
                (self.df_carreira['Data'] <= data_fim_mes)
            ]
            
            base_coronel = self.buscar_valor_coronel(data_inicio_mes)
            
            # CENÁRIO A: MÊS NORMAL (Sem mudança de posto)
            if promocao_no_mes.empty:
                posto_vigente = self.buscar_posto_na_data(data_inicio_mes)
                perc = self.escalonamento.get(posto_vigente, 0.0)
                fator_nivel = self.get_fator_nivel(posto_vigente, data_inicio_mes)
                
                valor_final = base_coronel * perc * fator_nivel
                
                return pd.Series([posto_vigente, valor_final])

            # CENÁRIO B: MÊS COM PROMOÇÃO (PRO RATA DIE)
            else:
                data_promo = promocao_no_mes.iloc[0]['Data']
                dia_promo = data_promo.day
                
                # Período A (Antigo)
                dias_antigos = dia_promo - 1
                data_fim_periodo_antigo = data_inicio_mes.replace(day=dias_antigos) if dias_antigos > 0 else data_inicio_mes
                
                # Período B (Novo)
                dias_novos = (ultimo_dia_numero - dia_promo) + 1
                
                posto_antigo = self.buscar_posto_na_data(data_inicio_mes)
                posto_novo = promocao_no_mes.iloc[0]['Posto']
                
                # Cálculo A
                perc_ant = self.escalonamento.get(posto_antigo, 0.0)
                nivel_ant = self.get_fator_nivel(posto_antigo, data_fim_periodo_antigo) 
                valor_diario_antigo = (base_coronel * perc_ant * nivel_ant) / ultimo_dia_numero
                total_antigo = valor_diario_antigo * dias_antigos
                
                # Cálculo B
                perc_nov = self.escalonamento.get(posto_novo, 0.0)
                nivel_nov = self.get_fator_nivel(posto_novo, data_fim_mes)
                valor_diario_novo = (base_coronel * perc_nov * nivel_nov) / ultimo_dia_numero
                total_novo = valor_diario_novo * dias_novos
                
                valor_final_pro_rata = total_antigo + total_novo
                
                texto_posto = f"{posto_antigo} ({dias_antigos}d) -> {posto_novo} ({dias_novos}d)"
                
                return pd.Series([texto_posto, valor_final_pro_rata])
            
    def consolidar_com_pdf(self, df_calculado, df_pdf):
        """
        Cruza a tabela 'ideal' (calculada pelo histórico) com a tabela 'real' (extraída do PDF).
        """
        # Garante tipagem de data para o cruzeiro
        df_pdf['Competencia'] = pd.to_datetime(df_pdf['Competencia'])
        df_calculado['Competencia'] = pd.to_datetime(df_calculado['Competencia'])

        # Prepara o PDF: Mantém apenas colunas essenciais e renomeia
        # Importante: O PDF já deve ter vindo daquela função 'extrair_dados_pdf' 
        # que agrupa e soma por competência.
        df_pdf_clean = df_pdf[['Competencia', 'Valor_Achado']].copy()
        df_pdf_clean = df_pdf_clean.rename(columns={'Valor_Achado': 'Valor_Pago_PDF'})

        # MERGE (Left Join):
        # A base é sempre o df_calculado (histórico). Se não tiver PDF no mês, fica NaN.
        df_final = pd.merge(df_calculado, df_pdf_clean, on='Competencia', how='left')

        # Substitui o Valor_Pago (que era 0.0) pelo valor do PDF
        # Se for NaN (não achou no PDF), preenche com 0.0
        df_final['Valor_Pago'] = df_final['Valor_Pago_PDF'].fillna(0.0)
        
        # Remove a coluna auxiliar
        df_final = df_final.drop(columns=['Valor_Pago_PDF'])

        # Recalcula a diferença agora com dados reais
        # Diferença = O que deveria receber (Devido) - O que recebeu (Pago)
        df_final['Diferenca_Mensal'] = df_final['Valor_Devido'] - df_final['Valor_Pago']
        
        # Opcional: Arredondar para evitar dízimas de ponto flutuante
        df_final['Diferenca_Mensal'] = df_final['Diferenca_Mensal'].round(2)

        return df_final
    # --- PROCESSAMENTO PRINCIPAL ---
    # --- NOVO GERAR_TABELA_BASE COMPLETO ---
    def gerar_tabela_base(self):
        df = self.gerar_timeline()
        
        # Aplica o cálculo Pro Rata linha a linha
        resultado_nominal = df.apply(self.calcular_valor_nominal_com_prorata, axis=1)
        
        # Joga o resultado nas colunas
        df['Posto_Vigente'] = resultado_nominal[0]
        df['Valor_Devido'] = resultado_nominal[1]
        
        df['Valor_Pago'] = 0.0 
        
        # 💡 CHAMA O NOVO MÉTODO AQUI:
        df = self.extrair_detalhes_laudo(df)
        
        return df

        # Passo 3: Pequeno Ajuste no `calcular_atualizacao` (Juros do 13º)
        # Como o 13º vence no dia 20/Dezembro, a regra de juros (Mês Seguinte / Jan) funciona bem com a nossa lógica padrão (que joga para o mês seguinte). Mas precisamos garantir que a data de referência para o IPCA (índice acumulado) funcione.


    def calcular_atualizacao(self, row):
        # --- LÓGICA FINANCEIRA (PRESERVADA) ---
        # Essa é a função que bateu com o Excel. Não mexemos nela!
        
        data_competencia = row['Competencia']
        valor_base = row['Diferenca_Mensal'] 
        data_ref_mes_atual = data_competencia.replace(day=1)
        
        if valor_base <= 0:
            return pd.Series([0.0, 0.0, 0.0, 0.0], index=['IPCA_Fator', 'Juros_Fator', 'Selic_Fator', 'Total_Final'])

        # Datas
        data_ref_ipca = data_competencia.replace(day=1)
        data_base_para_juros = data_competencia.replace(day=1)
        data_inicio_juros = data_base_para_juros + relativedelta(months=1)
        data_limite_fase1 = pd.to_datetime('2021-11-30')

        # 1. IPCA (Lê do CSV - Divisão Acumulada)
        fator_ipca = 1.0 # Valor padrão (se a data for posterior ao limite)

        if data_ref_ipca <= data_limite_fase1:
        # 1. Localiza o valor da CorrecaoMonetaria para a data específica
            fator_ipca = self.df_indices.loc[self.df_indices['Data'] == data_ref_ipca,'CorrecaoMonetaria'].values[0]
    
    
        # Se a condição for falsa (data > data_limite_fase1), fator_ipca permanece 1.0.
        # A cláusula 'else' não é mais necessária, pois fator_ipca já é 1.0 por padrão.

        # 2. Juros (Soma Simples)
        indices_futuros_juros = self.df_indices[self.df_indices['Data'] >= data_inicio_juros]
        fase1_juros = indices_futuros_juros[indices_futuros_juros['Data'] <= data_limite_fase1]
        
        fator_juros = (fase1_juros['JurosPoupanca'] / 100).sum() if not fase1_juros.empty else 0.0

        # 3. Selic (Soma Simples - Início na data da dívida se for nova)
        data_inicio_selic = max(data_ref_ipca, pd.to_datetime('2021-12-01'))
        fase2 = self.df_indices[self.df_indices['Data'] >= data_inicio_selic]
        
        fator_selic = (fase2['Selic'] / 100).sum() if not fase2.empty else 0.0

        valor_att = valor_base * fator_ipca
        valor_com_juros = valor_att * (1 + fator_juros)
        total_final = valor_com_juros * (1 + fator_selic)
        
        return pd.Series([fator_ipca, fator_juros, fator_selic, total_final], 
                         index=['IPCA_Fator', 'Juros_Fator', 'Selic_Fator', 'Total_Final'])

    def aplicar_financeiro(self, df_preenchido):
        df_preenchido['Diferenca_Mensal'] = df_preenchido['Valor_Devido'] - df_preenchido['Valor_Pago']
        df_preenchido['Diferenca_Mensal'] = df_preenchido['Diferenca_Mensal'].apply(lambda x: max(0.0, x))
        financeiro = df_preenchido.apply(self.calcular_atualizacao, axis=1)
        return pd.concat([df_preenchido, financeiro], axis=1)
