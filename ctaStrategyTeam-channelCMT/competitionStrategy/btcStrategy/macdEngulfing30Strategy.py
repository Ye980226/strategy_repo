from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
from datetime import datetime, timedelta
########################################################################
class macdEngulfing30Strategy(CtaTemplate):
    author = 'ChannelCMT'
    # 策略参数

    macdFastPeriod = 30; macdFastType = 0
    macdSlowPeriod= 60;macdSlowType=0
    macdSignalPeriod = 15;macdSignalType=3
    advShortPeriod = 2; advLongDelayPeriod = 4
    advMultiper = 1.12

    barPeriod = 200

    # 风控参数
    stopLossPct = 0.018; protectPct=0.015
    takeProfitFirstPct = 0.04; takeProfitSecondPct = 0.065
    holdHour =12;expectReturn = 0.001
    stopControlTime = 20

    # 仓位管理
    lot = 2

    # 策略变量
    transactionPrice = {}; openTime={};closeTime = {}
    macdTrend = {}; advTrend = {}
    stopProtect = {}

    # 自维护仓位与订单
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                'macdFastPeriod','macdFastType',
                'macdSlowPeriod', 'macdSlowType',
                'macdSignalPeriod', 'macdSignalType',
                'advShortPeriod', 'advLongDelayPeriod',
                'advMultiper','holdHour',
                'stopLossPct','protectPct', 'stopControlTime',
                'takeProfitFirstPct','takeProfitSecondPct', 'takeProfitThirdPct'
                ]
    # 变量列表，保存了变量的名称
    varList = [
               'macdTrend', 'advTrend',
               'transactionPrice','stopProtect',
               'ownPosDict','orderDict',
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
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.openTime = {s: None for s in self.symbolList}
        self.closeTime = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.stopProtect = {s: None for s in self.symbolList}
        self.tickObject = {s: None for s in self.symbolList}
        self.advTrend = {s: 0 for s in self.symbolList}
        self.macdTrend = {s: 0 for s in self.symbolList}


        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}
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

    # orderManagement--------------------------------------------------------
    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            for closeOrderId in list(self.orderDict[symbol + '_CLOSE']):
                self.cancelOrder(closeOrderId)

    def cancelOpenOrder(self, bar):
        symbol = bar.vtSymbol
        haveOpenOrder = len(self.orderDict[symbol + '_OPEN'])
        if haveOpenOrder:
            for openOrderId in list(self.orderDict[symbol + '_OPEN']):
                self.cancelOrder(openOrderId)

    def priceExecute(self, bar):
        symbol = bar.vtSymbol
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject[symbol].upperLimit - 0.5
            shortExecute = self.tickObject[symbol].lowerLimit + 0.5
        else:
            buyExecute = bar.close * 1.02
            shortExecute = bar.close * 0.98
        return buyExecute, shortExecute

    def buyCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelOpenOrder(bar)
        buyOpenOrderList = self.buy(symbol, buyExecute, volume)
        self.orderDict[symbol + '_OPEN'].extend(buyOpenOrderList)

    def shortCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelOpenOrder(bar)
        shortOpenOrderList = self.short(symbol, shortExecute, volume)
        self.orderDict[symbol + '_OPEN'].extend(shortOpenOrderList)

    def coverCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)
        coverCloseOrderList = self.cover(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)
        sellCloseOrderList = self.sell(symbol, shortExecute, self.ownPosDict[symbol + '_LONG'])
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def sellTakeProfitOrder(self, trade, price, volume):
        symbol = trade.vtSymbol
        sellCloseOrderList = self.sell(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def coverTakeProfitOrder(self, trade, price, volume):
        symbol = trade.vtSymbol
        coverCloseOrderList = self.cover(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        # 计算止损止盈价位
        self.onBarStopLoss(bar)

    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
#         print(bar.datetime,self.posDict)

        if self.closeTime[symbol]:
            if (bar.datetime - self.closeTime[symbol]) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl[symbol] = 0
        # 计算持有时间
        if self.openTime[symbol]:
            longUnexpect = (bar.close/self.transactionPrice[symbol]-1)<self.expectReturn
            shortUnexpect = (self.transactionPrice[symbol]/bar.close-1)<self.expectReturn
            if ((bar.datetime-self.openTime[symbol])>=timedelta(hours=self.holdHour)):
                if (self.posDict[symbol + "_LONG"] > 0) and longUnexpect:
                    self.sellCheckExtend(bar)
                    self.stopLossControl[symbol] = 1
                    print('longUnexpect')
                    self.writeCtaLog('afterOpenOrder_Sell')
                    self.openTime[symbol] = None
                elif (self.posDict[symbol + "_SHORT"] > 0) and shortUnexpect:
                    self.coverCheckExtend(bar)
                    self.stopLossControl[symbol] = -1
                    print('shortUnexpect')
                    self.writeCtaLog('afterOpenOrder_Cover')
                    self.openTime[symbol] = None


        # 计算止损价位
        buyStopLossPrice = self.transactionPrice[symbol] * (1 - self.stopLossPct)
        sellStopLossPrice = self.transactionPrice[symbol] * (1 + self.stopLossPct)
        buyProtectStopPrice = self.transactionPrice[symbol]*(1+self.protectPct)
        sellProtectStopPrice = self.transactionPrice[symbol]*(1-self.protectPct)

        if (self.ownPosDict[symbol + '_LONG'] == 0) and (self.ownPosDict[symbol + '_SHORT'] == 0):
            self.stopProtect[symbol] = 0
        elif (self.posDict[symbol + '_LONG'] > 0):
            #启动平保
            if (bar.low )>= buyProtectStopPrice:
                self.stopProtect[symbol] = 1
            if (self.stopProtect[symbol] == 1) and (bar.low <= (1.002 * self.transactionPrice[symbol])):
                self.sellCheckExtend(bar)
                self.stopLossControl[symbol] = 1
                self.stopProtect[symbol] = 0
            elif (self.stopProtect[symbol] == 0) and (bar.low <= buyStopLossPrice):
                self.sellCheckExtend(bar)
                self.stopLossControl[symbol] = 1

        elif (self.posDict[symbol + '_SHORT'] > 0):
            #启动平保
            if bar.high <= sellProtectStopPrice:
                self.stopProtect[symbol] = -1
            if (self.stopProtect[symbol] == -1) and (bar.high >= (0.998 * self.transactionPrice[symbol])):
                self.coverCheckExtend(bar)
                self.stopLossControl[symbol] = -1
                self.stopProtect[symbol] = 0
            elif (self.stopProtect[symbol] == 0) and (bar.high >= sellStopLossPrice):
                self.coverCheckExtend(bar)
                self.stopLossControl[symbol] = -1

    def on30MinBar(self, bar):
        symbol = bar.vtSymbol
        am30 = self.getArrayManager(symbol, "30m")
        if not am30.inited:
            return

        macd, macdSignal, macdHist = ta.MACDEXT(am30.close, self.macdFastPeriod, self.macdFastType, \
                                                self.macdSlowPeriod,self.macdSlowType, \
                                                self.macdSignalPeriod, self.macdSignalType)

        if macd[-1]>macdSignal[-1]:
            self.macdTrend[symbol] = 1
        elif macd[-1]<=macdSignal[-1]:
            self.macdTrend[symbol] = -1

    def on15MinBar(self, bar):
        """分钟K线推送"""
        symbol = bar.vtSymbol
        am15 = self.getArrayManager(symbol, "15m")
        if not am15.inited:
            return

        advShort = ta.MA(am15.volume,self.advShortPeriod)
        advLongDelay = ta.MA(am15.volume, self.advLongDelayPeriod)[:-self.advShortPeriod]*self.advMultiper

        if advShort[-1]>advLongDelay[-1]:
            self.advTrend[symbol] = 1
        elif advShort[-1]<=advLongDelay[-1]:
            self.advTrend[symbol] = -1

        # candleSignal
        ENGULFING = ta.CDLENGULFING(am15.open, am15.high, am15.low, am15.close)

        # phenomenon
        revertingUpS1 =  ENGULFING[-1]==100
        revertingDnS1 =  ENGULFING[-1]==-100


#         print(self.advTrend[symbol], self.macdTrend[symbol], revertingUpS1)
        if revertingUpS1 and (self.macdTrend[symbol]==1) \
        and (self.advTrend[symbol]==1) and (self.ownPosDict[symbol+'_LONG']==0):
            if self.stopLossControl[symbol] == -1:
                self.stopLossControl[symbol] = 0
            if (self.stopLossControl[symbol] == 0):
                if (self.ownPosDict[symbol + "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)

        elif revertingDnS1 and (self.macdTrend[symbol]==-1)\
        and (self.advTrend[symbol]==1) and (self.ownPosDict[symbol+'_SHORT']==0):
            if self.stopLossControl[symbol] == 1:
                self.stopLossControl[symbol] = 0
            if (self.stopLossControl[symbol] == 0):
                if (self.ownPosDict[symbol + "_LONG"] == 0):
                    self.shortCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_LONG"] > 0):
                    self.sellCheckExtend(bar)
                    self.shortCheckExtend(bar)

    # ----------------------------------------------------------------------

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        symbol = order.vtSymbol

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

        if order.status in STATUS_FINISHED:
            if order.offset == OFFSET_OPEN:
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif order.offset == OFFSET_CLOSE:
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s'\
                        %(trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        self.writeCtaLog('Quarter####diAdxStairStrategy:%s'%(symbol))
        print(trade.tradeDatetime, self.ownPosDict)
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
            self.openTime[symbol] = trade.tradeDatetime
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime[symbol] = trade.tradeDatetime
            self.openTime[symbol] = None
        # ownPosDict
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)

        # 发送止盈单
        longFirstProfit = self.transactionPrice[symbol]*(1+self.takeProfitFirstPct)
        longSecondProfit = self.transactionPrice[symbol]*(1+self.takeProfitSecondPct)
        shortFirstProfit = self.transactionPrice[symbol]*(1-self.takeProfitFirstPct)
        shortSecondProfit = self.transactionPrice[symbol]*(1-self.takeProfitSecondPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.cancelCloseOrder(trade)
                self.sellTakeProfitOrder(trade, longFirstProfit, trade.volume//2)
                self.sellTakeProfitOrder(trade, longSecondProfit, self.ownPosDict[symbol+'_LONG']-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.cancelCloseOrder(trade)
                self.coverTakeProfitOrder(trade, shortFirstProfit, trade.volume//2)
                self.coverTakeProfitOrder(trade, shortSecondProfit,self.ownPosDict[symbol+'_SHORT']-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass