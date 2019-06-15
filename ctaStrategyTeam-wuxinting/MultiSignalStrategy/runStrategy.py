import pandas as pd


from vnpy.trader.app.ctaStrategy import BacktestingEngine
from MultiSignalStrategy import MultiSignalStrategy

def runBacktesting(strategyClass, settingDict,
                   startDate, endDate, size, slippage, rate):
    engine = BacktestingEngine()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setDatabase('VnTrader_1Min_Db')
    engine.setStartDate(startDate, initHours=200)
    engine.setEndDate(endDate)
    engine.setSize(size)
    engine.setSlippage(slippage)
    engine.setRate(rate)
    engine.setLog(True, 'D:/xinge/log//')
    engine.initStrategy(strategyClass, settingDict)
    engine.setCapital(100000)
    engine.runBacktesting()
    # 显示逐日回测结果
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
    symbolList = [
#         'EOSUSDT:binance',
        # 'tEOSUSD:bitfinex',
        # 'eos_quarter:OKEX'
        # 'ETHUSDT:binance',
        # 'BCCUSDT:binance',
        'BTCUSDT:binance',
        # 'LTCUSDT:binance'
    ]


    from datetime import datetime
    start = datetime.now()
    performanceReport, tradeReport = \
        runBacktesting(MultiSignalStrategy, {'symbolList': symbolList},
                       '20180201 12:00', '20181201 12:00', 100, 0, 5/10000)
    # tradeReport.to_excel('CDL_LLT_AD_Strategy%s.xlsx'%(symbolList[0][:3]))
