from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta

########################################################################
class diAdxAtrStrategy(CtaTemplate):
    className = 'diAdxAtrStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 200
    adxPeriod = 20; adxMaPeriod = 30; adxMaType = 3; adxThreshold = 20
    plusDiPeriod = 20; minusDiPeriod = 20
    signalMaPeriod = 56; signalMaType = 0

    # 风控参数
    atrPeriod = 20; atrMultipler = 8; profitMultipler=2
    xTrend=1.2
    stopControlTime = 8; holdHour = 6
    lot = 100

    # 策略变量
    adxUp = {}; priceDirection = {}; signalMaDirection = {}
    transactionPrice = {}; openTime={}; closeTime = {}
    intraTradeHighDict = {}; intraTradeLowDict={}
    atr = {}; atrPos = {}
    longStop = {}; shortStop={}; stopLossControl = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'adxPeriod', 'adxMaPeriod', 'adxMaType', 'adxThreshold',
                 'plusDiPeriod', 'minusDiPeriod',
                 'signalMaPeriod', 'signalMaType',
                 'atrPeriod','atrMultipler','profitMultipler',
                 'xTrend', 'stopControlTime','holdHour'
                 ]

    # 变量列表，保存了变量的名称
    varList = ['posDict',
               'adxUp', 'priceDirection', 'signalMaDirection',
               'transactionPrice','lot',
               'stopLossControl', 'closeTime'
               ]
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略初始化')

        # signalVar
        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.adxUp = {s: 0 for s in self.symbolList}
        self.priceDirection = {s: 0 for s in self.symbolList}
        self.signalMaDirection = {s: 0 for s in self.symbolList}

        # riskControlVar
        self.atr = {s: 0 for s in self.symbolList}
        self.atrPos = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.closeTime = {s: 0 for s in self.symbolList}
        self.openTime = {s: None for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 999999 for s in self.symbolList}

        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略"""
        self.writeCtaLog(u'diAdx策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.writeCtaLog(u'diAdx策略停止')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        engineType = self.getEngineType()
        if engineType == 'trading':
            symbol = tick.vtSymbol
            self.tickObject[symbol] = tick
        else:
            pass

    def onBar(self, bar):
        self.writeCtaLog('diAdxAtrStrategy####5S####posDict:%s####'%(self.posDict))
        self.onBarRiskControl(bar)
        self.onBarExecute(bar)

    # ----------------------------------------------------------------------
#     def onBar(self, bar):
#         """收到Bar推送"""
#         pass

    def onBarRiskControl(self, bar):
        symbol = bar.vtSymbol
        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        atr = ta.ATR(am5.high, am5.low, am5.close, self.atrPeriod)[-1]


        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject[symbol].upperLimit-0.005
            shortExecute = self.tickObject[symbol].lowerLimit+0.005
        else:
            buyExecute = bar.close*1.01
            shortExecute = bar.close*0.99

        # afterStopLoss
        if self.closeTime[symbol]:
            if (bar.datetime - self.closeTime[symbol]) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl[symbol] = 0

        # afterOpenOrder
        if self.openTime[symbol]:
            if ((bar.datetime-self.openTime[symbol])>=timedelta(hours=self.holdHour)):
                if self.posDict[symbol + "_LONG"] > 0:
                    self.cancelAll()
                    self.sell(symbol, shortExecute, self.posDict[symbol + '_LONG'])
                    self.stopLossControl[symbol] = 1
                    self.openTime[symbol] = None
                elif self.posDict[symbol + "_SHORT"] > 0:
                    self.cancelAll()
                    self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                    self.stopLossControl[symbol] = -1
                    self.openTime[symbol] = None

        if self.posDict[symbol + "_LONG"] == 0 and self.posDict[symbol + "_SHORT"] == 0:
            self.atr[symbol] = 0
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
            self.longStop[symbol] = 0
            self.shortStop[symbol] = 999999

        # 持有多头仓位
        elif self.posDict[symbol + "_LONG"] > 0.5:
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop[symbol] = max(self.longStop[symbol], self.intraTradeHighDict[symbol]-self.atrMultipler*atr)
            takeProfit = self.transactionPrice[symbol]+self.profitMultipler*self.atrMultipler*self.atr[symbol]
            if bar.low <= self.longStop[symbol]:
                self.cancelAll()
                self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
                self.stopLossControl[symbol] = 1
            elif bar.high >= takeProfit:
                self.cancelAll()
                self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
                self.stopLossControl[symbol] = -1
#             print('longStop:', self.longStop[symbol])
        # 持有空头仓位
        elif self.posDict[symbol + "_SHORT"] > 0.5:
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop[symbol] = min(self.shortStop[symbol], self.intraTradeLowDict[symbol]+self.atrMultipler*atr)
            takeProfit = self.transactionPrice[symbol]-self.profitMultipler*self.atrMultipler*self.atr[symbol]
            if bar.high >= self.shortStop[symbol]:
                self.cancelAll()
                self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                self.stopLossControl[symbol] = -1
            elif bar.low <= takeProfit:
                self.cancelAll()
                self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                self.stopLossControl[symbol] = -1
#             print('shortStop:', self.shortStop[symbol])

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol

        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        atr = ta.ATR(am5.high, am5.low, am5.close, self.atrPeriod)[-1]

        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject[symbol].upperLimit-0.005
            shortExecute = self.tickObject[symbol].lowerLimit+0.005
        else:
            buyExecute = bar.close*1.01
            shortExecute = bar.close*0.99

        # canEntry
        if (self.adxUp[symbol] > 0):
            # buyCondition
            adxAtrLots = self.lot//self.adxUp[symbol]
            if (self.priceDirection[symbol] == 1) and (self.signalMaDirection[symbol]==1):
                if self.stopLossControl[symbol] == -1:
                    self.stopLossControl[symbol] = 0
                if (self.posDict[symbol + "_LONG"] == 0) and (self.stopLossControl[symbol] == 0):
                    if (self.posDict[symbol + "_SHORT"] == 0):
                        self.buy(symbol, buyExecute, adxAtrLots)
                        self.atr[symbol] = atr
                    elif (self.posDict[symbol + "_SHORT"] > 0):
                        self.cancelAll()
                        self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                        self.buy(symbol, buyExecute, adxAtrLots)
                        self.atr[symbol] = atr
            # sellCondition
            elif (self.priceDirection[symbol] == -1) and (self.signalMaDirection[symbol]==-1):
                if self.stopLossControl[symbol] == 1:
                    self.stopLossControl[symbol] = 0
                if (self.posDict[symbol + "_SHORT"] == 0) and (self.stopLossControl[symbol] == 0):
                    if (self.posDict[symbol + "_LONG"] == 0):
                        self.short(symbol, shortExecute, adxAtrLots)
                        self.atr[symbol] = atr
                    elif (self.posDict[symbol + "_LONG"] > 0):
                        self.cancelAll()
                        self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
                        self.short(symbol, shortExecute, adxAtrLots)
                        self.atr[symbol] = atr

        # exitCondition
        if (self.priceDirection[symbol] == -1) or (self.adxUp[symbol] == -1):  # parameter6
            if (self.posDict[symbol + "_LONG"] > 0.5) :
                self.cancelAll()
                self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
        if (self.priceDirection[symbol] == 1) or (self.adxUp[symbol] == -1):
            if self.posDict[symbol + "_SHORT"] > 0.5:
                self.cancelAll()
                self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
        # self.writeCtaLog(u'adxUp: %s ,priceDirection: %s'%(self.adxUp[symbol],self.priceDirection[symbol]))
        self.putEvent()

    # ----------------------------------------------------------------------
    def on60MinBar(self, bar):
        """60分钟K线推送"""
        symbol = bar.vtSymbol

        am60 = self.getArrayManager(symbol, "60m")

        if not am60.inited:
            return

        adxTrend = ta.ADX(am60.high, am60.low, am60.close, self.adxPeriod)
        adxMa = ta.MA(adxTrend, self.adxMaPeriod, matype=self.adxMaType)

        if (adxTrend[-1] > adxMa[-1]) and (adxTrend[-1]>=self.adxThreshold):
            if adxTrend[-1]<=30:
                self.adxUp[symbol] = 1
            elif adxTrend[-1]>30 and adxTrend[-1]<=40:
                self.adxUp[symbol] = 1.5*self.xTrend
            elif adxTrend[-1]>40 and adxTrend[-1]<=60:
                self.adxUp[symbol] = 2*self.xTrend
            elif adxTrend[-1]>60:
                self.adxUp[symbol] = 3*self.xTrend
        else:
            self.adxUp[symbol] = -1

        self.writeCtaLog(u'adxTrend[-1]: %s ,adxMa[-1]: %s'%(adxTrend[-1], adxMa[-1]))

        plusDi = ta.PLUS_DI(am60.high, am60.low, am60.close, self.plusDiPeriod)
        minusDi = ta.MINUS_DI(am60.high, am60.low, am60.close, self.plusDiPeriod)

        if (plusDi[-1]>minusDi[-1]):
            self.priceDirection[symbol] = 1
        else:
            self.priceDirection[symbol] = -1

        self.writeCtaLog(u'plusDi[-1]: %s ,minusDi[-1]: %s'%(plusDi[-1],minusDi[-1]))

    def on5MinBar(self, bar):
        symbol = bar.vtSymbol

        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        # signal
        signalMa = ta.MA(am5.close, self.signalMaPeriod, matype=self.signalMaType)

        if signalMa[-1]>signalMa[-2]:
            self.signalMaDirection[symbol] = 1
        elif signalMa[-1]<signalMa[-2]:
            self.signalMaDirection[symbol] = -1
        else:
            self.signalMaDirection[symbol] = 0

        self.writeCtaLog('signalMa[-1]:%s, signalMa[-1]:%s'%(signalMa[-1],signalMa[-2]))
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.thisTradedVolume != 0:
            # dealamount 不等于 0 表示有订单成交
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,posDict%s'\
                        %(trade.tradeTime, trade.offset, self.transactionPrice, self.posDict))
        if trade.offset == OFFSET_OPEN:
            engineType = self.getEngineType()
            if engineType == 'trading':
                self.transactionPrice[symbol] = trade.price_avg
            else:
                self.transactionPrice[symbol] = trade.price
            self.openTime[symbol] = trade.tradeTime
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime[symbol] = trade.tradeTime
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass