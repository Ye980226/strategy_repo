from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import numpy as np
from datetime import datetime, timedelta

########################################################################
class erEmaBreakStrategy(CtaTemplate):
    className = 'erEmaBreakStrategy'
    author = 'ChannelCMT'
    # 策略参数
    barPeriod = 200
    changeVolatilityPeriod = 60; erThrehold = 0.2
    erSemaPeriod = 30; erLemaPeriod=40
    emaHLPeriod = 30; maClosePeriod = 60
    lot = 2

    # 风控参数
    stopControlTime = 8
    stopLossPct = 0.025; protectPct=0.025
    takeProfitFirstPct = 0.03; takeProfitSecondPct = 0.04

    # 策略变量
    erTrend = 0
    transactionPrice = {}
    stopLossControl = 0
    stopProtect = 0
    # 参数列表，保存了参数的名称
    paramList = [
                 'changeVolatilityPeriod','erThrehold',
                 'erSemaPeriod','erLemaPeriod',
                 'emaHLPeriod','maClosePeriod',
                 'lot','stopControlTime',
                 'stopLossPct', 'protectPct',
                 'takeProfitFirstPct', 'takeProfitSecondPct']

    # 变量列表，保存了变量的名称
    varList = ['erTrend',
               'transactionPrice',
               'stopLossControl',
               'stopProtect']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']
    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(self.barPeriod)
        self.erTrend = 0
        self.transactionPrice = {s:0 for s in self.symbolList}
        self.tickObject = None
        self.closeTime = None
        self.openTime = None
        self.nChange = 0
        self.stopLossControl = 0

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
        # 策略恢复会自动读取 varList 和 syncList 的数据，还原之前运行时的状态。
        # 需要注意的是，使用恢复，策略不会运行 onInit 和 onStart 的代码，直接进入行情接收阶段
        self.putEvent()
    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        engineType = self.getEngineType()
        if engineType == 'trading':
            self.tickObject = tick
        else:
            pass

    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            for closeOrderId in list(self.orderDict[symbol + '_CLOSE']):
                self.cancelOrder(closeOrderId)

    def priceExecute(self, bar):
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject.upperLimit - 0.5
            shortExecute = self.tickObject.lowerLimit + 0.5
        else:
            buyExecute = bar.close * 1.02
            shortExecute = bar.close * 0.98
        return buyExecute, shortExecute

    def buyCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        if self.orderDict[symbol + '_OPEN']:
            self.writeCtaLog('haveOpenOrder_Pass')
        else:
            buyOpenOrderList = self.buy(symbol, buyExecute, volume)
            self.orderDict[symbol + '_OPEN'].extend(buyOpenOrderList)

    def shortCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        if self.orderDict[symbol + '_OPEN']:
            self.writeCtaLog('haveOpenOrder_Pass')
        else:
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
#     def onBar(self, bar):
    def on5sBar(self, bar):
        self.writeCtaLog('#####5s#####ownPosDict:%s#####'%(self.ownPosDict))
        self.onBarProtectStop(bar)
        self.onBarExecute(bar)
        self.onBarExitTimeControl(bar)

    def onBarProtectStop(self, bar):
        symbol = bar.vtSymbol
        # 计算止损止盈价位
        firstOrder = self.transactionPrice[symbol]
        buyStopLossPrice = firstOrder * (1 - self.stopLossPct)
        sellStopLossPrice = firstOrder * (1 + self.stopLossPct)
        buyProtectStopPrice = firstOrder*(1 + self.protectPct)
        sellProtectStopPrice = firstOrder*(1 - self.protectPct)

        if (self.ownPosDict[symbol + '_LONG'] == 0) and (self.ownPosDict[symbol + '_SHORT'] == 0):
            self.stopProtect = 0
        elif (self.ownPosDict[symbol + '_LONG'] > 0):
            if (bar.close)>= buyProtectStopPrice:
                self.stopProtect = 1
            if (self.stopProtect == 0):
                if (bar.low < buyStopLossPrice):
                    self.sellCheckExtend(bar)
                self.writeCtaLog('buyStopLossPrice:%s'%(buyStopLossPrice))
            elif self.stopProtect == 1:
                if bar.close <= (1.002 * firstOrder):
                    self.sellCheckExtend(bar)
                    self.stopProtect = 0

        elif (self.ownPosDict[symbol + '_SHORT'] > 0):
            if bar.close <= sellProtectStopPrice:
                self.stopProtect = -1
            if (self.stopProtect == 0):
                if (bar.high > sellStopLossPrice):
                    self.coverCheckExtend(bar)
                self.writeCtaLog('sellStopLossPrice:%s'%(sellStopLossPrice))
            elif (self.stopProtect == -1):
                if (bar.close >= (0.998 * firstOrder)):
                    self.coverCheckExtend(bar)
                    self.stopProtect = 0

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        am15 = self.getArrayManager(symbol, "15m")
        am = self.getArrayManager(symbol, "1m")

        if (not am15.inited) or (not am.inited):
            return

        # indicator
        emaHigh = ta.EMA(am15.high, self.emaHLPeriod)
        emaLow = ta.EMA(am15.low, self.emaHLPeriod)
        maClose = ta.MA(am15.close, self.maClosePeriod)

        # phenomenon
        emaHighBreak = (am.high[-1]>=emaHigh[-2]) and (am.high[-2]<emaHigh[-2])
        emaLowBreak = (am.low[-1]<=emaLow[-2]) and (am.low[-2]>emaLow[-2])
        maCloseUp = maClose[-1]>maClose[-3]
        maCloseDn = maClose[-1]<maClose[-3]

        self.writeCtaLog('high:%s, emaHigh:%s, low:%s, emaLow:%s'%(am.high[-2:], emaHigh[-2], am.low[-2:], emaLow[-2]))

        # order
        if (emaHighBreak) and (self.erTrend==1) \
        and maCloseUp and (self.ownPosDict[symbol+'_LONG']==0):
            if self.stopLossControl==-1:
                self.stopLossControl=0
            if self.stopLossControl==0:
                if  (self.ownPosDict[symbol+'_SHORT']==0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol+'_SHORT'] > 0):
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)
        elif (emaLowBreak) and (self.erTrend==1) \
        and maCloseDn and (self.ownPosDict[symbol+'_SHORT']==0):
            if self.stopLossControl==1:
                self.stopLossControl=0
            if self.stopLossControl==0:
                if (self.ownPosDict[symbol+'_LONG']==0):
                    self.shortCheckExtend(bar)
                elif (self.ownPosDict[symbol+'_LONG'] > 0):
                    self.sellCheckExtend(bar)
                    self.shortCheckExtend(bar)

    def onBarExitTimeControl(self, bar):
        if self.closeTime:
            if (bar.datetime - self.closeTime) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl = 0

    def on15MinBar(self, bar):
        pass

    def on30MinBar(self, bar):
        """分钟K线推送"""
        symbol = bar.vtSymbol
        am30 = self.getArrayManager(symbol, "30m")
        if not am30.inited:
            return

        change = np.abs(am30.close[self.changeVolatilityPeriod:]-am30.close[:-self.changeVolatilityPeriod])
        volatility = ta.SUM(np.abs(am30.close[1:]-am30.close[:-1]), self.changeVolatilityPeriod)
        er = change[-120:]/volatility[-120:]
        erSma = ta.EMA(er, self.erSemaPeriod)
        erLma = ta.MA(er, self.erLemaPeriod)

        # phenomenon
        erUp = (erSma[-1]>erLma[-1])
        erThrehold = (erSma[-1]>self.erThrehold)

        # signal
        if erUp and erThrehold:
            self.erTrend = 1
        else:
            self.erTrend = -1

        self.writeCtaLog('erSma:%s, erLma:%s'%(erSma[-1], erLma[-1]))
        self.putEvent()

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
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
#         print(order.status, self.orderDict)

        if order.status in STATUS_FINISHED:
            if order.offset == OFFSET_OPEN:
                self.orderDict[symbol+'_OPEN'].remove(str(order.vtOrderID))
            elif order.offset == OFFSET_CLOSE:
                self.orderDict[symbol+'_CLOSE'].remove(str(order.vtOrderID))

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        symbol = trade.vtSymbol
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
            self.openTime = trade.tradeDatetime
            self.closeTime = None
        elif trade.offset == OFFSET_CLOSE:
            self.openTime = None
            self.closeTime = trade.tradeDatetime

            if trade.direction == DIRECTION_SHORT:
                self.stopLossControl = 1
            elif trade.direction == DIRECTION_LONG:
                self.stopLossControl = -1

        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol+'_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol+'_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol+'_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol+'_SHORT'] -= int(trade.volume)
        self.takeProfit(trade)
        print(trade.tradeTime, self.ownPosDict)

    def takeProfit(self, trade):
        # 发送止盈单
        symbol = trade.vtSymbol
        longFirstProfit = self.transactionPrice[symbol]*(1+self.takeProfitFirstPct)
        longSecondProfit = self.transactionPrice[symbol]*(1+self.takeProfitSecondPct)
        shortFirstProfit = self.transactionPrice[symbol]*(1-self.takeProfitFirstPct)
        shortSecondProfit = self.transactionPrice[symbol]*(1-self.takeProfitSecondPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellTakeProfitOrder(trade, longFirstProfit, trade.volume//2)
                self.sellTakeProfitOrder(trade, longSecondProfit, trade.volume-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.coverTakeProfitOrder(trade, shortFirstProfit, trade.volume//2)
                self.coverTakeProfitOrder(trade, shortSecondProfit,trade.volume-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass