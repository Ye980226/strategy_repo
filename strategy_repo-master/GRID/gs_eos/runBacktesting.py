# encoding: UTF-8
"""
展示如何执行策略回测。
"""
from vnpy.trader.app.ctaStrategy import BacktestingEngine
import pandas as pd
from vnpy.trader.utils import htmlplot
import json
import logging

if __name__ == '__main__':

    print('消除了log所有的warning输出')
    logging.basicConfig(level=logging.ERROR)

    from StrategySlopeGrid import StrategySlopeGrid
    # 创建回测引擎
    engine = BacktestingEngine()
    logging.basicConfig(level=logging.ERROR)

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)
    # 设置使用的历史数据库
    engine.setDatabase('VnTrader_1Min_Db')

    # 设置回测用的数据起始日期，initHours 默认值为 0
    engine.setStartDate('20190501 08:00:00',initHours=1)   
    engine.setEndDate('20190524 08:00:00')
    # engine.setDB_URI('mongodb://192.168.0.104:27017')
    # 设置产品相关参数
    engine.setCapital(1000)  # 设置起始资金，默认值是1,000,000
    contracts = [
        {
        "symbol":'eos.usd.q:okef',
        "size" : 10,
        "priceTick" : 0.001,
        "rate" : 5/10000,
        "slippage" : 0.001
        }
        ]
    engine.setContracts(contracts)     # 设置回测合约相关数据
    engine.setLog(True, "./log") 

    # 在引擎中创建策略对象
    
    with open("CTA_setting.json") as parameterDict:
        d = json.load(parameterDict)[0]

    engine.initStrategy(StrategySlopeGrid, d)
    # 开始跑回测
    engine.runBacktesting()
    print('runBacktesting finish-----------------')

    engine.showDailyResult()
    engine.showBacktestingResult() 
    
    ### 画图分析
    mp = htmlplot.getMultiPlot(engine, freq="5m")
    mp.show()