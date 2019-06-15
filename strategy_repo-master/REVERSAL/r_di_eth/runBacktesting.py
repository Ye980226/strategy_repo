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
    from StrategyETH_DI import Strategy_signalDI
    # 创建回测引擎
    engine = BacktestingEngine()
    logging.basicConfig(level=logging.ERROR)

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)
    # 设置使用的历史数据库
    engine.setDatabase('VnTrader_1Min_Db')

    # 设置回测用的数据起始日期，initHours 默认值为 0
    engine.setStartDate('20180602 06:00:00',initHours=120)   
    engine.setEndDate('20190513 06:00:00')
    engine.setDB_URI('mongodb://192.168.0.104:27017')
    # 设置产品相关参数
    engine.setCapital(1000)  # 设置起始资金，默认值是1,000,000
    contracts = [
        {
        "symbol":'eth.usd.q:okef',
        "size" : 10,
        "priceTick" : 0.001,
        "rate" : 5/10000,
        "slippage" : 0.001
        }
        ]
    engine.setContracts(contracts)     # 设置回测合约相关数据
    engine.setLog(True, "./log") 
     # engine.setCachePath("C:\\Users\\Administrator\\Desktop\\回测用文件\\backData")  # 设置本地数据缓存的路径，默认存在用户文件夹内

    # 在引擎中创建策略对象
    with open("CTA_setting.json") as f:
        d = json.load(f)[0]

    engine.initStrategy(Strategy_signalDI, d)
    
    # 开始跑回测
    engine.runBacktesting()
    
    # 显示回测结果
    engine.showDailyResult()
    engine.showBacktestingResult()
    
    ### 画图分析
    # dilog = pd.DataFrame(engine.strategy.dilog)  
    # atr = pd.DataFrame(engine.strategy.atr)
    # mp = htmlplot.getMultiPlot(engine, freq="15m")
    # mp.set_line(line=dilog, colors={"di": "red",'dima':'blue','di_line2':'green'})
    # mp.set_line(line=atr)
    # mp.show()
 