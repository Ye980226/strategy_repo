import pandas as pd
# from MultiFrameMa import MultiFrameMaStrategy
# from BollCciAtr import BollChannelStrategy
# from adxVwapStrategy import adxVwapStrategy
# from MultiSignal import MultiSignalStrategy
# from rsiTrendReverting import rsiTrendReverting

from vnpy.trader.app.ctaStrategy.ctaBacktesting import BacktestingEngine, OptimizationSetting, MINUTE_DB_NAME

# from strategy_hy import MultiSignalHYStrategy
from strategy_shark_1 import FishStrategy
# from Ma_strategy import break_Strategy

# from BollBandExample import BBandsMethod1Strategy

# from SecondBreak15 import SecondBreakStrategy
import pandas as pd

def runBacktesting(strategyClass, settingDict,
                   startDate, endDate, size, slippage, rate):
    engine = BacktestingEngine()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setDatabase('VnTrader_1Min_Db')
    engine.setStartDate(startDate, initHours=100)
    engine.setEndDate(endDate)
    engine.setSize(size)
    engine.setSlippage(slippage)
    engine.setRate(rate)
    engine.initStrategy(strategyClass, settingDict)
    engine.setCapital(100000)
    engine.runBacktesting()
    #显示逐日回测结果
    engine.showDailyResult()
    #显示逐笔回测结果
    engine.showBacktestingResult()
    # 计算回测结果
    perfromance = engine.calculateDailyResult()
    perfromanceDf , result = engine.calculateDailyStatistics(perfromance)
    tradeReport = pd.DataFrame([obj.__dict__ for obj in engine.tradeDict.values()])
    tradeDf = tradeReport.set_index('dt')
    return perfromanceDf, tradeDf

if __name__ == '__main__':
    performanceReport, tradeReport = \
        runBacktesting(FishStrategy, {'symbolList': ['BTCUSDT:binance',
                                                            # 'eth_quanter:OKEX'
                                                            ]},
                       '20180101 12:00', '20180925 12:00', 100, 0, 5/10000)
    tradeReport.to_excel('FishStrategyReport.xlsx')