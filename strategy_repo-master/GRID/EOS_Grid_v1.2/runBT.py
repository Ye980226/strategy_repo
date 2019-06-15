import json

import pandas
from vnpy.trader.app.ctaStrategy import BacktestingEngine
from vnpy.trader.utils import htmlplot

def runBacktesting(strategyClass, settingDict,
                   startDate, endDate, contracts):
    engine = BacktestingEngine()
    # engine.setBacktestingMode(engine.TICK_MODE)  # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)  # 设置引擎的回测模式为K线
    engine.setDB_URI("mongodb://192.168.0.104:27017")
    engine.setDatabase('VnTrader_1Min_Db')  # 设置使用的历史数据库
    engine.setStartDate(startDate)  # 设置回测用的数据起始日期
    engine.setEndDate(endDate)  # 设置回测用的数据结束日期
    engine.setContracts(contracts)  # 设置回测合约相关数据
    engine.setCapital(100000)  # 设置回测本金
    engine.setLog(True, "./log")
    engine.initStrategy(strategyClass, settingDict)
    engine.runBacktesting()

    # pandas.DataFrame(engine.strategy.value).to_csv("spread.csv")

    # 显示逐日回测结果
    engine.showDailyResult()
    # 显示逐笔回测结果
    engine.showBacktestingResult()
    # # data = pandas.read_csv("sig_eos.csv", index_col=0)
    # # data["datetime"] = data["datetime"].apply(lambda x: pandas.to_datetime(x))
    # # mp = htmlplot.getMultiPlot(engine, freq="1h")
    # # mp.set_line(line=data[["datetime",
    # #                        "K","Ksd"
    # #                        ]])
    # # mp.set_line(line=data[["datetime",
    # #                        "adx"
    # #                        ]])
    # # mp.show()
    #
    htmlplot.showTransaction(engine, frequency="5m")


from Strategy import StrategyEOSGridV12

with open("./CTA_setting.json") as f:
    setting = json.load(f)[0]

contracts = [
    {
        "symbol": "eos.usd.q:okef",
        "rate": 5 / 10000,  # 单边手续费
        "slippage": 0.002  # 滑价
    },

]

runBacktesting(StrategyEOSGridV12, setting,
               '20190301 00:00:00', '20190513 23:59:00',
               contracts=contracts)
