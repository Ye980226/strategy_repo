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

    # pandas.DataFrame(engine.strategy.value).to_csv("sig.csv")

    # 显示逐日回测结果
    engine.showDailyResult()
    # 显示逐笔回测结果
    engine.showBacktestingResult()
    # data = pandas.read_csv("sig.csv", index_col=0)
    # data["datetime"] = data["datetime"].apply(lambda x: pandas.to_datetime(x))
    # mp = htmlplot.getMultiPlot(engine, freq="1m")
    # mp.set_line(line=data[["datetime",
    #                        "ATR"]])
    # mp.set_vbar(data=data[["datetime",
    #                        "prop"]])
    # mp.set_vbar(data=data[["datetime",
    #                       "initlot"]])
    # mp.show()

    htmlplot.showTransaction(engine, frequency="15m")


from Strategy import StrategyHighRangeRevV2

# slippage: btc 0.5 eth/ltc:0.05 eos:0.002
contracts = [
    {
        "symbol": "eth.usd.q:okef",
        "rate": 5 / 10000,  # 单边手续费
        "slippage": 0.005  # 滑价
    },
]

setting_file_path = "./%s.json" % (contracts[0]["symbol"].replace(".", "_").replace(":", "_"))
with open(setting_file_path) as f:
    setting = json.load(f)[0]

runBacktesting(StrategyHighRangeRevV2, setting,
               '20190501 00:00:00', '20190531 23:59:00',
               contracts=contracts)
