"""
展示如何执行策略回测。
"""
from vnpy.trader.app.ctaStrategy import BacktestingEngine
import pandas as pd
from vnpy.trader.utils import htmlplot
import json
import os

if __name__ == '__main__':
    from bsAtrStrategyV2 import bsAtrStrategy
    # 创建回测引擎

    engine = BacktestingEngine()
    engine.setDB_URI("mongodb://192.168.0.104:27017")

    # Bar回测
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setDatabase('VnTrader_1Min_Db')

    # Tick回测
    # engine.setBacktestingMode(engine.TICK_MODE)
    # engine.setDatabase('VnTrader_1Min_Db', 'VnTrader_Tick_Db')

    # 设置回测用的数据起始日期，initHours 默认值为 0
    engine.setStartDate('20180601 23:00:00',initHours=10)   
    engine.setEndDate('20190620 23:00:00')

    # 设置产品相关参数
    engine.setCapital(100)  # 设置起始资金，默认值是1,000,000
    contracts = [{
                    "symbol":"eth.usd.q:okef",
                    "size" : 1, # 每点价值
                    "priceTick" : 0.01, # 最小价格变动
                    "rate" : 5/10000, # 单边手续费
                    "slippage" : 0.1 # 滑价
                    },] 

    engine.setContracts(contracts)
    engine.setLog(True, "../../../backtestingLog")
    
    path = os.path.split(os.path.realpath(__file__))[0]
    with open(path+"//CTA_setting.json") as parameterDict:
        setting = json.load(parameterDict)
    
    print(setting[0])
    # Bar回测
    setting[0]['symbolList'] = ["eth.usd.q:okef"]
    
    # Tick回测
    # setting[0]['symbolList'] = ["eth_quarter:OKEX"]
    
    engine.initStrategy(bsAtrStrategy, setting[0])
    
    # 开始跑回测
    engine.runBacktesting()
    
    # 显示回测结果
    engine.showBacktestingResult()
    engine.showDailyResult()
    
    ### 画图分析
    chartDf = pd.DataFrame(engine.strategy.chartLog).drop_duplicates().set_index('datetime')
    print(chartDf.tail())
    mp = htmlplot.getMultiPlot(engine, freq="5m")
    # mp.set_line(line=chartDf[['upperBand', 'lowerBand', 'sma', 'lma']], colors={"upperBand": "red", "lowerBand": "green", 'sma': 'yellow', 'lma':'blue' }, pos=0)
    mp.show()
 