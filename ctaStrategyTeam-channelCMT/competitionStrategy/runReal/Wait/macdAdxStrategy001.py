from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time

########################################################################
class macdAdxStrategy(CtaTemplate):
    className = 'diAdxStairStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 200
    adxPeriod = 30; adxMaType = 0; adxThreshold = 25
    fastPeriod = 15; slowPeriod = 30; signalPeriod = 10
    fastMaType = 0; slowMaType = 0; signalMaType = 2

    # 风控参数
    trailingPct = 0.02; stopControlTime = 4
    takeProfitFirstPct = 0.035; takeProfitSecondPct = 0.05
    lot = 2

    # 仓位管理参数
    addPct = 0.004; addMultipler = 0.8

    # 策略变量
    adxCanTrade = {}; priceDirection = {}
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
                 'adxPeriod', 'adxMaType', 'adxThreshold',
                 'fastPeriod', 'slowPeriod','signalPeriod',
                 'fastMaType', 'slowMaType', 'signalMaType',
                 'trailingPct', 'stopControlTime',
                 'addPct','addMultipler','lot',
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'adxCanTrade', 'priceDirection', 'signalMaDirection',
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
        self.adxCanTrade = {s: 0 for s in self.symbolList}
        self.priceDirection = {s: 0 for s in self.symbolList}

        # riskControlVar
        self.transactionPrice = {s+'0': 0 for s in self.symbolList}
        self.closeTime = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 999999 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}

        # posManage
        self.nPos = {s: 0 for s in self.symbolList}

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
        if not self.dataBlock(dataTime=tick.datetime, now=datetime.now(), maxDelay=5):
            engineType = self.getEngineType()
            if engineType == 'trading':
                symbol = tick.vtSymbol
                self.tickObject[symbol] = tick
            else:
                pass

    # 过滤掉实盘推数据可能产生的阻塞(5s延迟)
    def dataBlock(self, dataTime, now, maxDelay=5):
        if abs(now - dataTime).total_seconds() > maxDelay:
            self.writeCtaLog(
                "数据推送阻塞,跳过该次推送:now=%s,dataTime=%s" % (now.strftime("%Y-%m-%d %H:%M:%S"),
                                                      dataTime.strftime("%Y-%m-%d %H:%M:%S")))
            return True
        else:
            return False

    # orderManagement--------------------------------------------------------
    def timeSleep(self):
        engineType=self.getEngineType()
        if engineType == 'trading':
            time.sleep(3)
        else:
            return

    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            for closeOrderId in list(self.orderDict[symbol + '_CLOSE']):
                self.cancelOrder(closeOrderId)
            self.timeSleep()
        else:
            return

    def cancelOpenOrder(self, bar):
        symbol = bar.vtSymbol
        haveOpenOrder = len(self.orderDict[symbol + '_OPEN'])
        if haveOpenOrder:
            for openOrderId in list(self.orderDict[symbol + '_OPEN']):
                self.cancelOrder(openOrderId)
            self.timeSleep()
        else:
            return

    def priceExecute(self, bar):
        symbol = bar.vtSymbol
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject[symbol].upperLimit*0.99
            shortExecute = self.tickObject[symbol].lowerLimit*1.01
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

# executeManagement--------------------------------------------------------
#     def on5sBar(self, bar):
    def onBar(self, bar):
        self.writeCtaLog('diAdxStairStrategy####5S####ownposDict:%s####'%(self.ownPosDict))
        self.onBarRiskControl(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

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
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.nChange[symbol] = (self.intraTradeHighDict[symbol]/firstOrder-1)//self.trailingPct
            changePrice = firstOrder*self.nChange[symbol]*self.trailingPct
            self.longStop[symbol] = max(self.longStop[symbol], firstOrder*(1-self.trailingPct)+changePrice)
            if bar.low <= self.longStop[symbol]:
                self.sellCheckExtend(bar)
            self.writeCtaLog('longStop%s'%(self.longStop[symbol]))
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.nChange[symbol] = -1* (self.intraTradeLowDict[symbol]/firstOrder-1)//self.trailingPct
            changePrice = firstOrder*self.nChange[symbol]*self.trailingPct
            self.shortStop[symbol] = min(self.shortStop[symbol], firstOrder*(1+self.trailingPct)-changePrice)
            if bar.high >= self.shortStop[symbol]:
                self.coverCheckExtend(bar)
            self.writeCtaLog('shortStop%s'%(self.shortStop[symbol]))

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if (self.priceDirection[symbol] == -1):  # parameter6
            if (self.ownPosDict[symbol + "_LONG"] > 0) :
                self.sellCheckExtend(bar)

        elif (self.priceDirection[symbol] == 1):
            if self.ownPosDict[symbol + "_SHORT"] > 0:
                self.coverCheckExtend(bar)

        if (self.adxCanTrade[symbol] == 1):
            if (self.priceDirection[symbol] == 1) and (self.ownPosDict[symbol + "_LONG"] == 0):
                if self.stopLossControl[symbol] == -1:
                    self.stopLossControl[symbol] = 0
                if (self.stopLossControl[symbol] == 0):
                    if (self.ownPosDict[symbol + "_SHORT"] == 0):
                        self.buyCheckExtend(bar)
                    elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                        self.coverCheckExtend(bar)
                        self.buyCheckExtend(bar)

            elif (self.priceDirection[symbol] == -1) and (self.ownPosDict[symbol + "_SHORT"] == 0):
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
        firstOrder=self.transactionPrice[symbol+'0']
        if (self.ownPosDict[symbol+'_LONG']==0) and (self.ownPosDict[symbol + "_SHORT"]==0):
            self.nPos[symbol]=0
        elif (self.ownPosDict[symbol+'_LONG']>0 and self.nPos[symbol] < 1):
            if (firstOrder/bar.close-1) >= self.addPct:
                self.nPos[symbol] += 1
                self.buyCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos[symbol])))
        elif (self.ownPosDict[symbol + "_SHORT"] > 0 and self.nPos[symbol] < 1):
            if (bar.close/firstOrder-1) >= self.addPct:
                self.nPos[symbol] += 1
                self.shortCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos[symbol])))


    # ----------------------------------------------------------------------
    def on60MinBar(self, bar):
        symbol = bar.vtSymbol

        am60 = self.getArrayManager(symbol, "60m")

        if not am60.inited:
            return

        adxTrend = ta.ADX(am60.high, am60.low, am60.close, self.adxPeriod)

        # Status
        if (adxTrend[-1]<=self.adxThreshold):
            self.adxCanTrade[symbol] = 1
        else:
            self.adxCanTrade[symbol] = -1

        self.writeCtaLog('adxTrend: %s, adxCanTrade: %s:'%(adxTrend[-1], self.adxCanTrade[symbol]))

        macd, macdSignal, macdHist = ta.MACDEXT(am60.close, self.fastPeriod, self.fastMaType, \
                                                self.slowPeriod, self.slowMaType, self.signalPeriod, self.signalMaType)

        if (macd[-1]>macdSignal[-1]) and (macd[-1]>macd[-3]):
            self.priceDirection[symbol] = 1
        elif (macd[-1]<macdSignal[-1]) and (macd[-1]<macd[-3]):
            self.priceDirection[symbol] = -1
        else:
            self.priceDirection[symbol] = 0

        self.writeCtaLog(u'macd: %s, macdSignal: %s, priceDirection: %s'%(macd[-3:], macdSignal[-1], self.priceDirection[symbol]))


    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        symbol = order.vtSymbol

        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
        if order.thisTradedVolume != 0:
            # dealamount 不等于 0 表示有订单成交
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

        if order.status in STATUS_FINISHED:
            if (order.offset == OFFSET_OPEN) and (str(order.vtOrderID) in self.orderDict[symbol + '_OPEN']):
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif (order.offset == OFFSET_CLOSE) and (str(order.vtOrderID) in self.orderDict[symbol + '_CLOSE']):
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s'\
                        %(trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        self.writeCtaLog('Quarter####diAdxStairStrategy:%s'%(symbol))
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol+'%s'%self.nPos[symbol]] = trade.price
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime[symbol] = trade.tradeDatetime
            if trade.direction == DIRECTION_SHORT:
                self.stopLossControl[symbol] = 1
            elif trade.direction == DIRECTION_LONG:
                self.stopLossControl[symbol] = -1

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
        longFirstProfit = self.transactionPrice[symbol+'%s'%self.nPos[symbol]]*(1+self.takeProfitFirstPct)
        longSecondProfit = self.transactionPrice[symbol+'%s'%self.nPos[symbol]]*(1+self.takeProfitSecondPct)
        shortFirstProfit = self.transactionPrice[symbol+'%s'%self.nPos[symbol]]*(1-self.takeProfitFirstPct)
        shortSecondProfit = self.transactionPrice[symbol+'%s'%self.nPos[symbol]]*(1-self.takeProfitSecondPct)


        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellTakeProfitOrder(trade, longFirstProfit, trade.volume//2)
                self.sellTakeProfitOrder(trade, longSecondProfit, trade.volume-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.coverTakeProfitOrder(trade, shortFirstProfit, trade.volume//2)
                self.coverTakeProfitOrder(trade, shortSecondProfit,trade.volume-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
        print(trade.tradeDatetime, self.ownPosDict)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass