"""
展示如何执行策略回测。
"""
from vnpy.trader.app.ctaStrategy import BacktestingEngine
import pandas as pd
from vnpy.trader.utils import htmlplot
import json

if __name__ == '__main__':
    from outsideCandleStrategy510 import outsideCandleStrategy
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
    engine.setStartDate('20190315 23:00:00',initHours=10)   
    engine.setEndDate('20190531 23:00:00')

    # 设置产品相关参数
    engine.setCapital(1000)  # 设置起始资金，默认值是1,000,000
    contracts = [{
                    "symbol":"btc.usd.q:okef",
                    "size" : 1, # 每点价值
                    "priceTick" : 0.001, # 最小价格变动
                    "rate" : 5/10000, # 单边手续费
                    "slippage" : 0.5 # 滑价
                    },] 

    engine.setContracts(contracts)
    engine.setLog(True, "../../../log") 
    
    with open("CTA_setting.json") as parameterDict:
        setting = json.load(parameterDict)
    
    print(setting[0])
    
    engine.initStrategy(outsideCandleStrategy, setting[0])
    
    # 开始跑回测
    engine.runBacktesting()
    
    # 显示回测结果
    engine.showBacktestingResult()
    engine.showDailyResult()
    
    ### 画图分析
    chartDf = pd.DataFrame(engine.strategy.chartLog).drop_duplicates().set_index('datetime')
    mp = htmlplot.getMultiPlot(engine, freq="1m")
    mp.set_vbar(chartDf[['volume']], freq=None, colors='green', pos=1)
    mp.set_line(line=chartDf[['volumeUpper']], colors={"volumeUpper": "red"}, pos=1)    
    mp.set_line(line=chartDf[['rsi']], colors={"rsi": "red"}, pos=2)    
    mp.show()
 