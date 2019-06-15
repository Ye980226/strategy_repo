# 残差变化率的均线上涨
from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
from datetime import datetime, timedelta


########################################################################
class regEmaBreakStrategy(CtaTemplate):
    className = 'regEmaBreakStrategy'
    author = 'ChannelCMT'
    # 策略参数
    barPeriod = 200
    regPeriod = 50
    residualSmaPeriod = 18; residualLmaPeriod = 30
    emaHighPeriod = 10; emaLowPeriod = 10
    ta.MA()
    # 风控参数
    stopControlTime = 24
    atrMultipler = 8; atrPeriod = 20; profitMultiper = 2

    # 仓位管理
    lot = 100; addPct = 0.006; addMultiper = 1

    # 策略变量
    regTrend = {}; atrTrade = {}
    transactionPrice = {}; closeTime={}
    intraTradeHighDict = {}; intraTradeLowDict = {}
    longStop = {}; shortStop = {}
    nPos = {}

    # 参数列表，保存了参数的名称
    paramList = ['regPeriod',
                 'residualSmaPeriod','residualLmaPeriod',
                 'emaHighPeriod', 'emaLowPeriod',
                 'stopControlTime',
                 'atrMultipler', 'atrPeriod','profitMultiper',
                 'lot', 'addPct', 'addMultiper',
                 ]
    # 变量列表，保存了变量的名称
    varList = [
               'regTrend', 'atrTrade',
               'transactionPrice','closeTime',
               'nPos'
              ]

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']
    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.regTrend = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 999999 for s in self.symbolList}
        self.atrTrade = {s: 0 for s in self.symbolList}
        self.closeTime = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.nPos = {s: 0 for s in self.symbolList}

        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()  # putEvent 能刷新策略UI界面的信息
    # ----------------------------------------------------------------------

    def onStart(self):
        """启动策略"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.putEvent()
    # ----------------------------------------------------------------------
    def onRestore(self):
        """恢复策略"""
        # 策略恢复会自动读取 varList 和 syncList 的数据，还原之前运行时的状态。
        # 需要注意的是，使用恢复，策略不会运行 onInit 和 onStart 的代码，直接进入行情接收阶段
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
    # ----------------------------------------------------------------------
    def on5sBar(self, bar):
        """收到Bar推送"""
        self.writeCtaLog('regressionEmaBreakStrategy####5S####posDict:%s####'%(self.posDict))
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

    def onBar(self, bar):
        pass

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        am30 = self.getArrayManager(symbol, "30m")
        am = self.getArrayManager(symbol, "5s")

        if (not am30.inited) and (not am.inited):
            return

        # indicator
        emaHigh = ta.EMA(am30.high, self.emaHighPeriod)
        emaLow = ta.EMA(am30.low, self.emaLowPeriod)
        atr = ta.ATR(am30.high, am30.low, am30.close, 10)[-1]
        # phenomenon
        emaLowUp = (am.low[-1]>emaLow[-2])
        emaHighDn = (am.high[-1]<emahigh[-2])

        # order
        buyExecute = self.tickObject[symbol].upperLimit-0.005
        shortExecute = self.tickObject[symbol].lowerLimit+0.005
        if (emaLowUp) and (self.regTrend[symbol]==1) and (self.posDict[symbol+'_LONG']==0):
            if self.stopLossControl[symbol]==-1:
                self.stopLossControl[symbol]=0
            if self.stopLossControl[symbol]==0:
                if  (self.posDict[symbol+'_SHORT']==0):
                    self.buy(symbol, buyExecute, self.lot)  # 成交价*1.01发送高价位的限价单，以最优市价买入进场
                    self.atrTrade[symbol] = atr
                elif (self.posDict[symbol+'_SHORT'] > 0.5):
                    self.cancelAll() # 撤销挂单
                    self.cover(symbol, buyExecute, self.posDict[symbol+'_SHORT'])
                    self.buy(symbol, buyExecute, self.lot)
                    self.atrTrade[symbol] = atr

        if (emaHighDn) and (self.regTrend[symbol]==-1) and (self.posDict[symbol+'_SHORT']==0):
            if self.stopLossControl[symbol]==1:
                self.stopLossControl[symbol]=0
            if self.stopLossControl[symbol]==0:
                if (self.posDict[symbol+'_LONG']==0):
                    self.short(symbol, shortExecute, self.lot) # 成交价*0.99发送低价位的限价单，以最优市价卖出进场
                    self.atrTrade[symbol] = atr
                elif (self.posDict[symbol+'_LONG'] > 0.5):
                    self.cancelAll() # 撤销挂单
                    self.sell(symbol, shortExecute, self.posDict[symbol+'_LONG'])
                    self.short(symbol, shortExecute, self.lot)
                    self.atrTrade[symbol] = atr
        # exit
        if (self.regTrend[symbol]==-1):
            if (self.posDict[symbol+'_LONG']>0.5):
                self.cancelAll()
                self.sell(symbol, shortExecute, self.posDict[symbol+'_LONG'])
                self.writeCtaLog('signalLongExit')
        elif (self.regTrend[symbol]==1):
            if (self.posDict[symbol+'_SHORT']>0.5):
                self.cancelAll()
                self.cover(symbol, buyExecute, self.posDict[symbol+'_SHORT'])
                self.writeCtaLog('signalShortExit')
        self.writeCtaLog('(high:%s, emaHigh:%s), (low:%s, emaLow:%s), self.regTrend[symbol]%s'%(bar.high, emaHigh[-1], bar.low, emaLow[-1], self.regTrend[symbol]))

    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
        am30 = self.getArrayManager(symbol, "30m")

        if (not am30.inited):
            return

        if self.closeTime[symbol]:
            if (bar.datetime - self.closeTime[symbol]) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl[symbol] = 0

        atr = ta.ATR(am30.high, am30.low, am30.close, 10)[-1]
        # 变量初始化
        buyExecute = self.tickObject[symbol].upperLimit-0.005
        shortExecute = self.tickObject[symbol].lowerLimit+0.005
        if self.posDict[symbol + "_LONG"] == 0 and self.posDict[symbol + "_SHORT"] == 0:
            self.atrTrade[symbol] = 0
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
            self.longStop[symbol] = 0
            self.shortStop[symbol] = 999999
        # 持有多头仓位
        elif self.posDict[symbol + "_LONG"] > 0.5:
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop[symbol] = max(self.longStop[symbol], self.intraTradeHighDict[symbol]-self.atrMultipler*atr)
            takeProfit = self.transactionPrice[symbol]+self.profitMultiper*self.atrMultipler*self.atrTrade[symbol]
            if bar.low <= self.longStop[symbol]:
                self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
                self.stopLossControl[symbol] = 1
                self.writeCtaLog('longStop:%s'%self.longStop[symbol])
            elif bar.high> takeProfit:
                self.sell(symbol, shortExecute, self.posDict[symbol + "_LONG"])
                self.writeCtaLog('takeProfit:%s'%takeProfit)
        # 持有空头仓位
        elif self.posDict[symbol + "_SHORT"] > 0.5:
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop[symbol] = min(self.shortStop[symbol], self.intraTradeLowDict[symbol]+self.atrMultipler*atr)
            takeProfit = self.transactionPrice[symbol]-self.profitMultiper*self.atrMultipler*self.atrTrade[symbol]
            if bar.high >= self.shortStop[symbol]:
                self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                self.stopLossControl[symbol] = -1
                self.writeCtaLog('shortStop:%s'%self.shortStop[symbol])
            elif bar.low < takeProfit:
                self.cover(symbol, buyExecute, self.posDict[symbol + "_SHORT"])
                self.writeCtaLog('takeProfit:%s'%takeProfit)
        self.putEvent()  # 每分钟更新一次UI界面


    def on30MinBar(self, bar):
        pass

    def on60MinBar(self, bar):
        """分钟K线推送"""
        symbol = bar.vtSymbol
        am60 = self.getArrayManager(symbol, "60m")
        if not am60.inited:
            return

        prediction = ta.LINEARREG(am60.close, self.regPeriod)
        residual = (am60.close - prediction) / am60.close
        residualSma = ta.MA(residual, self.residualSmaPeriod)
        residualLma = ta.MA(residual, self.residualLmaPeriod)

        # phenomenon
        residualUp = residualSma[-1] > residualLma[-1]
        residualDn = residualSma[-1] < residualLma[-1]

        # signal
        if residualUp:
            self.regTrend[symbol] = 1
        elif residualDn:
            self.regTrend[symbol] = -1
        else:
            self.regTrend[symbol] = 0
        self.writeCtaLog('residualSma%s, residualLma:%s'%(residualSma[-1],  residualLma[-1]))

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
        symbol = trade.vtSymbol
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onTrade
        self.writeCtaLog('self.nPos[symbol]:%s'%(self.nPos[symbol]))
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,posDict%s'\
                 %(trade.tradeTime, trade.offset, self.transactionPrice, self.posDict))
        if trade.offset == OFFSET_OPEN:  # 判断成交订单类型
            self.transactionPrice[symbol] = trade.price_avg # 记录成交价格
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime[symbol] = trade.tradeTime
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass