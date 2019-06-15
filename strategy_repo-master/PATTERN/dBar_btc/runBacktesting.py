# encoding: UTF-8
"""
展示如何执行策略回测。
"""
from vnpy.trader.app.ctaStrategy import BacktestingEngine
import pandas as pd
import os
from strategydoublebar import Strategydoublebar as StrategyClass
import json
import logging
from datetime import datetime, timedelta

def strategyBacktesting(start,end):
    # 创建回测引擎
    engine = BacktestingEngine()
    logging.basicConfig(level=logging.ERROR)
    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)
    # 设置使用的历史数据库
    engine.setDatabase('VnTrader_1Min_Db')
    # 设置回测用的数据起始日期，initHours 默认值为 0
    engine.setStartDate(start,initHours=1)   
    engine.setEndDate(end)
    engine.setDB_URI('mongodb://192.168.0.104:27017')
    # 设置产品相关参数
    engine.setCapital(1000)  # 设置起始资金，默认值是1,000,000
    with open("CTA_setting.json") as parameterDict:
        d = json.load(parameterDict)[0]   
    contracts = []
    for symbol in d['symbolList']:
        
        contracts.append({
            'symbol':symbol,
            'size':10,
            'priceTick':0.001,
            'rate':8/10000,
            'slippage':0
        })

    engine.setContracts(contracts)     # 设置回测合约相关数据
    engine.setLog(True, "./log") 
    # 在引擎中创建策略对象
    with open("CTA_setting.json") as parameterDict:
        d = json.load(parameterDict)[0]
    engine.initStrategy(StrategyClass, d)
    # 开始跑回测
    engine.runBacktesting()
    print('runBacktesting finish-----------------')
    engine.showDailyResult()
    engine.showBacktestingResult() 

    return engine

if __name__ == '__main__':
    
    date = datetime(datetime.now().year, datetime.now().month, datetime.now().day)
    today = datetime.strftime(date,'%Y%m%d %H:%M:%S')
    past3month = datetime.strftime(date-timedelta(days=90),'%Y%m%d %H:%M:%S')
    ### 以20180602为起点的回测
    engine1year = strategyBacktesting('20180601 08:00:00',today)

    ### 回测过去3个月的绩效
    engine3month = strategyBacktesting(past3month,today)
    
    # ### 画图分析
    plotengine = engine3month
    from vnpy.trader.utils import htmlplot
    candel=pd.DataFrame([bar.__dict__ for bar in plotengine.backtestData])
    trade_file = os.path.join(plotengine.logPath, "交割单.csv")
    trades = htmlplot.read_transaction_file(trade_file)
    mp = htmlplot.MultiPlot(os.path.join(plotengine.logPath, "transaction.html"))
    mp.set_main(candel, trades, "15m")
    mp.show()    
