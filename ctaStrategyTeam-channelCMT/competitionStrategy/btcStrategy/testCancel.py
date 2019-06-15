from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta

########################################################################
class diAdxStairStrategy(CtaTemplate):
    className = 'diAdxStairStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 200
    plusDiPeriod = 90; minusDiPeriod = 80
    adxPeriod = 30; adxMaPeriod = 40; adxMaType = 0; adxThreshold = 14
    signalMaPeriod = 70; signalMaType = 2

    # 风控参数
    trailingPct = 0.026; stopControlTime = 12
    takeProfitFirstPct = 0.05; takeProfitSecondPct = 0.07
    lot = 100

    # 仓位管理参数
    addPct = 0.003; addMultipler = 1.1


    # 策略变量
    adxUp = {}; priceDirection = {}; signalMaDirection = {}
    transactionPrice = {}; closeTime = {}
    stopLossControl = {}; nChange = {}
    intraTradeHighDict = {}; intraTradeLowDict = {}
    longStop = {}; shortStop = {}
    nPos = {}

    # 自维护仓位与订单
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'adxPeriod', 'adxMaPeriod', 'adxMaType', 'adxThreshold',
                 'plusDiPeriod', 'minusDiPeriod',
                 'signalMaPeriod', 'signalMaType',
                 'trailingPct', 'stopControlTime',
                 'addPct','addMultipler','lot',
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'adxUp', 'priceDirection', 'signalMaDirection',
               'transactionPrice',
               'stopLossControl'
               ]
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)


    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        # signalVar
        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.adxUp = {s: 0 for s in self.symbolList}
        self.priceDirection = {s: 0 for s in self.symbolList}
        self.signalMaDirection = {s: 0 for s in self.symbolList}

        # riskControlVar
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.closeTime = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 999999 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}

        # posManage
        nPos = {s: 0 for s in self.symbolList}

        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}

        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略停止')
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

        ##################
        coverCloseOrderList = self.cover(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)

        ################
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

# executeManagement--------------------------------------------------------
#     def on5sBar(self, bar):
    def onBar(self, bar):
        self.writeCtaLog('diAdxStairStrategy####5S####posDict:%s####'%(self.ownPosDict))
        self.onBarRiskControl(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

    # ----------------------------------------------------------------------
#     def onBar(self, bar):
#         pass

    def onBarRiskControl(self, bar):
        symbol = bar.vtSymbol

        if self.closeTime[symbol]:
            if (bar.datetime - self.closeTime[symbol]) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl[symbol] = 0

        if self.ownPosDict[symbol + "_LONG"] == 0 and self.ownPosDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
            self.longStop[symbol] = 0
            self.shortStop[symbol] = 999999
            self.nChange[symbol] = 0

        # 持有多头仓位
        elif self.ownPosDict[symbol + "_LONG"] > 0:
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.nChange[symbol] = (self.intraTradeHighDict[symbol]/self.transactionPrice[symbol]-1)//self.trailingPct
            changePrice = self.transactionPrice[symbol]*self.nChange[symbol]*self.trailingPct
            self.longStop[symbol] = max(self.longStop[symbol], self.transactionPrice[symbol]*(1-self.trailingPct)+changePrice)
            if bar.low <= self.longStop[symbol]:
                self.sellCheckExtend(bar)
                self.stopLossControl[symbol] = 1
            self.writeCtaLog('longStop%s'%(self.longStop[symbol]))
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.nChange[symbol] = -1* (self.intraTradeLowDict[symbol]/self.transactionPrice[symbol]-1)//self.trailingPct
            changePrice = self.transactionPrice[symbol]*self.nChange[symbol]*self.trailingPct
            self.shortStop[symbol] = min(self.shortStop[symbol], self.transactionPrice[symbol]*(1+self.trailingPct)-changePrice)
            if bar.high >= self.shortStop[symbol]:
                self.coverCheckExtend(bar)
                self.stopLossControl[symbol] = -1
            self.writeCtaLog('shortStop%s'%(self.shortStop[symbol]))

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol

        if (self.priceDirection[symbol] == -1) or (self.adxUp[symbol] == -1):  # parameter6
            if (self.ownPosDict[symbol + "_LONG"] > 0) :
                self.sellCheckExtend(bar)

        if (self.priceDirection[symbol] == 1) or (self.adxUp[symbol] == -1):
            if self.ownPosDict[symbol + "_SHORT"] > 0:
                self.coverCheckExtend(bar)

        if (self.adxUp[symbol] == 1):
            if (self.priceDirection[symbol] == 1) and (self.signalMaDirection[symbol]==1) \
            and (self.ownPosDict[symbol + "_LONG"] == 0):
                if self.stopLossControl[symbol] == -1:
                    self.stopLossControl[symbol] = 0
                if (self.stopLossControl[symbol] == 0):
                    if (self.ownPosDict[symbol + "_SHORT"] == 0):
                        self.buyCheckExtend(bar)
                    elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                        self.coverCheckExtend(bar)
                        self.buyCheckExtend(bar)

            elif (self.priceDirection[symbol] == -1) and (self.signalMaDirection[symbol]==-1)\
            and (self.ownPosDict[symbol + "_SHORT"] == 0):
                if self.stopLossControl[symbol] == 1:
                    self.stopLossControl[symbol] = 0
                if (self.stopLossControl[symbol] == 0):
                    if (self.ownPosDict[symbol + "_LONG"] == 0):
                        self.shortCheckExtend(bar)
                    elif (self.ownPosDict[symbol + "_LONG"] > 0):
                        self.sellCheckExtend(bar)
                        self.shortCheckExtend(bar)
        self.putEvent()

    def onBarPosition(self,bar):
        symbol = bar.vtSymbol
        lastOrder=self.transactionPrice[symbol]
        if (self.ownPosDict[symbol+'_LONG']==0) and (self.ownPosDict[symbol + "_SHORT"]==0):
            self.nPos[symbol]=0
        elif (self.ownPosDict[symbol+'_LONG']>0 and self.nPos[symbol] < 1):
            if (lastOrder/bar.close-1) >= self.addPct:
                self.nPos[symbol] += 1
                self.buyCheckExtend(bar, self.lot*(self.addMultipler**self.nPos[symbol]))
        elif (self.ownPosDict[symbol + "_SHORT"] > 0 and self.nPos[symbol] < 1):
            if (bar.close/lastOrder-1) >= self.addPct:
                self.nPos[symbol] += 1
                self.shortCheckExtend(bar, self.lot*(self.addMultipler**self.nPos[symbol]))


    # ----------------------------------------------------------------------
    def on30MinBar(self, bar):
        """30分钟K线推送"""
        symbol = bar.vtSymbol

        am30 = self.getArrayManager(symbol, "30m")

        if not am30.inited:
            return

        adxTrend = ta.ADX(am30.high, am30.low, am30.close, self.adxPeriod)
        adxMa = ta.MA(adxTrend, self.adxMaPeriod, matype=self.adxMaType)

        # Status

        if (adxTrend[-1] > adxMa[-1]) and (adxTrend[-1]>=self.adxThreshold):
            self.adxUp[symbol] = 1
        else:
            self.adxUp[symbol] = -1

        self.writeCtaLog(u'adxTrend[-1]: %s ,adxMa[-1]: %s'%(adxTrend[-1], adxMa[-1]))

        plusDi = ta.PLUS_DI(am30.high, am30.low, am30.close, self.plusDiPeriod)
        minusDi = ta.MINUS_DI(am30.high, am30.low, am30.close, self.minusDiPeriod)

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
        print(self.ownPosDict)
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime[symbol] = trade.tradeDatetime

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
                ############################
                self.sellTakeProfitOrder(trade, longFirstProfit, trade.volume//2)
                self.sellTakeProfitOrder(trade, longSecondProfit, self.ownPosDict[symbol+'_LONG']-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.cancelCloseOrder(trade)
                ############################
                self.coverTakeProfitOrder(trade, shortFirstProfit, trade.volume//2)
                self.coverTakeProfitOrder(trade, shortSecondProfit,self.ownPosDict[symbol+'_SHORT']-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass