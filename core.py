import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar

class CalculadoraMilitar:
    def __init__(self, data_ingresso, data_ajuizamento, historico_promocoes):
        # 1. Configurações
        self.data_ingresso = pd.to_datetime(data_ingresso, dayfirst=True)
        self.data_ajuizamento = pd.to_datetime(data_ajuizamento, dayfirst=True)
        self.data_corte_selic = pd.to_datetime('2021-12-01') # Marco da EC 113
        
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
            cols_financeiras = ['IPCA', 'Selic', 'JurosPoupanca', 'FatorAcumulado'] 
            for col in cols_financeiras:
                if col in self.df_indices.columns:
                    self.df_indices[col] = self.df_indices[col].astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False)
                    self.df_indices[col] = pd.to_numeric(self.df_indices[col], errors='coerce').fillna(0.0)
            
            self.df_indices = self.df_indices.sort_values('Data')

            # Captura Numerador IPCA (Nov/21) - Lógica que bateu com Excel
            try:
                data_nov21 = pd.to_datetime('2021-11-01')
                self.indice_ref_nov21 = self.df_indices.loc[self.df_indices['Data'] == data_nov21, 'FatorAcumulado'].values[0]
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
        inicio = self.data_ajuizamento - relativedelta(years=5)
        if inicio < self.data_ingresso: inicio = self.data_ingresso
        
        # --- CORREÇÃO DA DATA FINAL (EXIGIBILIDADE) ---
        # Não podemos calcular o mês corrente pois o pagamento ainda não ocorreu.
        # Definimos o fim como o primeiro dia do MÊS ANTERIOR ao atual.
        # Ex: Se hoje é 04/12/2025, calculamos até 01/11/2025.
        data_hoje = datetime.today()
        fim = data_hoje.replace(day=1) - relativedelta(months=1)
        
        # Garante que não dê erro se a data final for menor que a inicial (recém ingressado)
        if fim < inicio:
            fim = inicio

        # Gera a linha do tempo até o mês fechado anterior
        datas = pd.date_range(start=inicio, end=fim, freq='MS') 
        return pd.DataFrame({'Competencia': datas})

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
        """ Calcula o multiplicador do Nível (Triênio/Equivalência) - PRESERVADO """
        posto = str(posto).upper().strip()
        if posto == "NÃO INGRESSOU": return 1.0
        
        # Regras de Exceção (Bolsas Fixas - Aluno e Aspirante)
        if "ASPIRANTE" in posto or "ASP." in posto: return 1.00
        if "ALUNO CFO" in posto:
            if "3" in posto or "III" in posto: return 1.06
            elif "2" in posto or "II" in posto: return 1.06
            elif "1" in posto or posto.endswith(" I"): return 1.03
            return 1.03 # Padrão

        # Regra Geral (3% a cada 3 anos)
        # Calcula tempo de serviço até o último dia do mês para ser justo
        #ultimo_dia = data_referencia + relativedelta(day=31)
        anos = relativedelta(data_referencia, self.data_ingresso).years
        return 1 + (int(anos / 3) * 0.03)

    # --- NOVO: LÓGICA PRO RATA DIE ---
    def calcular_valor_nominal_com_prorata(self, row):
        """
        Calcula o valor devido no mês. 
        Se houver promoção NO MEIO do mês, calcula proporcionalmente aos dias.
        """
        data_inicio_mes = row['Competencia'] # Dia 01
        
        # Descobre o último dia do mês (28, 29, 30 ou 31)
        ultimo_dia_numero = calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1]
        data_fim_mes = data_inicio_mes.replace(day=ultimo_dia_numero)
        
        # 1. Verifica se houve promoção DENTRO deste mês
        # A promoção tem que ser > dia 01 e <= dia final
        promocao_no_mes = self.df_carreira[
            (self.df_carreira['Data'] > data_inicio_mes) & 
            (self.df_carreira['Data'] <= data_fim_mes)
        ]
        
        # Busca Valor Base do Coronel para este mês
        base_coronel = self.buscar_valor_coronel(data_inicio_mes)
        
        # --- CENÁRIO 1: MÊS NORMAL (Sem mudança de posto) ---
        if promocao_no_mes.empty:
            posto_vigente = self.buscar_posto_na_data(data_inicio_mes)
            perc = self.escalonamento.get(posto_vigente, 0.0)
            fator_nivel = self.get_fator_nivel(posto_vigente, data_inicio_mes)
            
            valor_final = base_coronel * perc * fator_nivel
            
            return pd.Series([posto_vigente, valor_final])

        # --- CENÁRIO 2: MÊS COM PROMOÇÃO (PRO RATA DIE) ---
        else:
            # Pega a data da promoção
            data_promo = promocao_no_mes.iloc[0]['Data']
            dia_promo = data_promo.day
            
            # Definindo os períodos
            # Periodo A (Antigo): Do dia 1 até o dia anterior à promoção
            dias_antigos = dia_promo - 1
            # Defina a data exata do fim do período antigo (dia anterior à promoção)
            data_fim_periodo_antigo = data_inicio_mes.replace(day=dias_antigos)
            
            # Periodo B (Novo): Da data da promoção até o fim do mês
            dias_novos = (ultimo_dia_numero - dia_promo) + 1
            
            # Postos
            posto_antigo = self.buscar_posto_na_data(data_inicio_mes) # Dia 01
            posto_novo = promocao_no_mes.iloc[0]['Posto'] # O posto da promoção
            
            # Cálculo A (Antigo)
            perc_ant = self.escalonamento.get(posto_antigo, 0.0)
            nivel_ant = self.get_fator_nivel(posto_antigo, data_fim_periodo_antigo) 
            valor_diario_antigo = (base_coronel * perc_ant * nivel_ant) / ultimo_dia_numero
            total_antigo = valor_diario_antigo * dias_antigos
            
            # Cálculo B (Novo)
            perc_nov = self.escalonamento.get(posto_novo, 0.0)
            nivel_nov = self.get_fator_nivel(posto_novo, data_fim_mes)
            valor_diario_novo = (base_coronel * perc_nov * nivel_nov) / ultimo_dia_numero
            total_novo = valor_diario_novo * dias_novos
            
            valor_final_pro_rata = total_antigo + total_novo
            
            # Retorna o texto indicando a mudança para ficar bonito na tabela
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
    def gerar_tabela_base(self):
        df = self.gerar_timeline()
        
        # Aplica o cálculo Pro Rata linha a linha
        resultado_nominal = df.apply(self.calcular_valor_nominal_com_prorata, axis=1)
        
        # Joga o resultado nas colunas
        df['Posto_Vigente'] = resultado_nominal[0]
        df['Valor_Devido'] = resultado_nominal[1]
        
        df['Valor_Pago'] = 0.0 
        return df

    def calcular_atualizacao(self, row):
        # --- LÓGICA FINANCEIRA (PRESERVADA) ---
        # Essa é a função que bateu com o Excel. Não mexemos nela!
        
        data_competencia = row['Competencia']
        valor_base = row['Diferenca_Mensal'] 
        
        if valor_base <= 0:
            return pd.Series([0.0, 0.0, 0.0, 0.0], index=['IPCA_Fator', 'Juros_Fator', 'Selic_Fator', 'Total_Final'])

        # Datas
        data_ref_ipca = data_competencia.replace(day=1)
        data_inicio_juros = data_competencia + relativedelta(months=1)
        data_limite_fase1 = pd.to_datetime('2021-11-30')

        # 1. IPCA (Lê do CSV - Divisão Acumulada)
        fator_ipca = 1.0
        if data_ref_ipca <= data_limite_fase1:
            try:
                indice_data = self.df_indices.loc[self.df_indices['Data'] == data_ref_ipca, 'FatorAcumulado'].values[0]
                if indice_data > 0:
                    fator_ipca = self.indice_ref_nov21 / indice_data
            except: fator_ipca = 1.0

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
