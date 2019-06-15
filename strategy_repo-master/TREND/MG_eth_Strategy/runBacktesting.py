"""
展示如何执行策略回测。
"""
from vnpy.trader.app.ctaStrategy import BacktestingEngine
import pandas as pd
from vnpy.trader.utils import htmlplot
import json
import logging

if __name__ == '__main__':
    from MG_eth_Strategy import MAGlueStrategy
    # 创建回测引擎
    logging.basicConfig(level=logging.ERROR)
    engine = BacktestingEngine()
    engine.setDB_URI("mongodb://192.168.0.104:27017")
    #engine.setDB_URI("mongodb://localhost:27017")    

    # Bar回测
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setDatabase('VnTrader_1Min_Db')

    # Tick回测
    # engine.setBacktestingMode(engine.TICK_MODE)
    # engine.setDatabase('VnTrader_1Min_Db', 'VnTrader_Tick_Db')

    # 设置回测用的数据起始日期，initHours 默认值为 0
    engine.setStartDate('20190101 01:00:00',initHours=10)   
    engine.setEndDate('20190528 23:00:00')

    # 设置产品相关参数
    engine.setCapital(1000000)  # 设置起始资金，默认值是1,000,000
    contracts = [{
                    "symbol":"eth.usd.q:okef",
                    "size" : 1, # 每点价值
                    "priceTick" : 0.001, # 最小价格变动
                    "rate" : 5/10000, # 单边手续费
                    "slippage" : 0.002 # 滑价
                    },] 

    engine.setContracts(contracts)
    engine.setLog(True, "../log") 
    
    with open("CTA_setting.json") as parameterDict:
        setting = json.load(parameterDict)

    print(setting[0])
    # Bar回测
    setting[0]['symbolList'] = ["eth.usd.q:okef"]
    
    # Tick回测
    # setting[0]['symbolList'] = ["btc_quarter:OKEX"]
    
    engine.initStrategy(MAGlueStrategy, setting[0])
    
    # 开始跑回测
    engine.runBacktesting()
    
    # 显示回测结果
    engine.showBacktestingResult()
    engine.showDailyResult()
    
    ### 画图分析
    chartDf = pd.DataFrame(engine.strategy.chartLog).drop_duplicates().set_index('datetime')
    print(chartDf.tail())
    mp = htmlplot.getMultiPlot(engine, freq="5m")
    mp.set_line(line=chartDf[['agg_value','throld']], colors={"agg_value": "green",'throld':'blue'}, pos=1)
    mp.set_line(line=chartDf[['SMa','LMa']], colors={"SMa": "red","LMa":"black"}, pos=2)
    mp.show()
 