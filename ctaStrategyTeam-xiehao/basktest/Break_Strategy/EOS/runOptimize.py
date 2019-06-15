from vnpy.trader.app.ctaStrategy.ctaBacktesting import BacktestingEngine, OptimizationSetting, MINUTE_DB_NAME
import pandas as pd
import time
# from MultiFrameMa import MultiFrameMaStrategy
# from BollCciAtr import BollChannelStrategy
# from adxVwapStrategy import adxVwapStrategy
# from rsiTrendReverting import rsiTrendReverting
# from BollSingle import BBandsMethod1Strategy
from Ma_strategy import break_Strategy


def runOptimize(strategyClass, settingDict,
                   startDate, endDate, slippage,
                   rate, size, target='sharpeRatio'):
    engine = BacktestingEngine()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setDatabase(MINUTE_DB_NAME)
    engine.setStartDate(startDate, initHours=24)
    engine.setEndDate(endDate)
    engine.setSize(size)
    engine.setSlippage(slippage)
    engine.setRate(rate)
    engine.initStrategy(strategyClass, settingDict)
    engine.setCapital(100000)
    engine.runBacktesting()

    # 优化配置
    setting = OptimizationSetting()                 # 新建一个优化任务设置对象
    setting.setOptimizeTarget(target)        # 设置优化排序的目标是策略净盈利
# addParameter-----------------------------------------------------------------------------------------
    setting.addParameter('symbolList', ['EOSUSDT:binance'])
    # setting.addParameter('trendFastWindow', 10, 29, 5)
    # setting.addParameter('breakday', 5, 30, 5)
    # setting.addParameter('ccivalue', 2, 20, 2)
    setting.addParameter('Window1', 12, 33, 3)
    setting.addParameter('Window2', 17, 41, 3)
    # setting.addParameter('cciPeriod', 8, 40, 4)
    # setting.addParameter('profitMultiplier', 2, 6, 1)
    #
    # arrayWindow = 100
    # breakWindow = 50
    # secondWindow = 50
    # holdMinute = 500
    # atrMultiplier = 10  # 止损比例
    # profitMultiplier = 2

    # 执行多进程优化
    start = time.time()
    resultList = engine.runParallelOptimization(strategyClass, setting)
    # resultList = engine.runOptimization(MultiFrameMaStrategy, setting)
    print('耗时：%s' %(time.time()-start))
    bestParameter = pd.DataFrame(resultList).sort_values(1,  ascending=False).iloc[0:20]
    return bestParameter

if __name__ == '__main__':
    # bestParameter = runOptimize(MultiFrameMaStrategy, {'symbolList':['BTCUSD:binance']} , '20180301', '20180630', 0.2, 1/1000, 1, 0.01)
    bestParameter = runOptimize(break_Strategy, {'symbolList': ['EOSUSDT:binance']} , '20180601 12:00', '20180918 12:00', 0.002, 5/10000, 100)
    bestParameter.to_excel('SecondBreak15StrategyParameter.xlsx')