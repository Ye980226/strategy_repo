from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time

########################################################################
class adxKdjBtcStrategy(CtaTemplate):
    className = 'adxKdjBtcStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 200
    adxPeriod = 55; adxEntryThreshold = 22; adxExitThreshold=24
    fastkPeriod = 100; slowkPeriod = 40; slowdPeriod = 60
    slowkMaType = 0; slowdMaType = 1
    overBought = 30; overSold = 70

    # 风控参数
    trailingPct = 0.03; stopControlTime = 4
    takeProfitFirstPct = 0.035; takeProfitSecondPct = 0.045
    lot = 20

    # 仓位管理参数
    addPct = 0.002; addMultipler = 0.5

    # 信号变量
    adxCanTrade = 0; filterCanTrade=0
    priceDirection = 0
    stopLossControl = 0

    transactionPrice={}
    # 自维护仓位与订单
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'adxPeriod', 'adxEntryThreshold', 'adxExitThreshold',
                 'fastkPeriod', 'slowkPeriod','slowdPeriod',
                 'slowkMaType', 'slowdMaType',
                 'overBought','overSold',
                 'trailingPct', 'stopControlTime',
                 'addPct','addMultipler','lot',
                 'takeProfitFirstPct', 'takeProfitSecondPct'
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'adxCanTrade', 'priceDirection',
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
        self.tickObject = None

        # riskControlVar
        self.transactionPrice = {s+'0': 0 for s in self.symbolList}
        self.closeTime = None
        self.longStop = 0
        self.shortStop = 999999
        self.intraTradeHighDict = 0
        self.intraTradeLowDict = 999999

        # posManage
        self.nPos = 0

        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}

        # 订单管理
        self.toExcuteOrders = {}
        self.toExcuteOrdersID = 0
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
                self.tickObject = tick
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
    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            canceling = list(self.orderDict[symbol + '_CLOSE'])
            for closeOrderId in canceling:
                self.cancelOrder(closeOrderId)
            return False, canceling
        else:
            return True, []

    def priceExecute(self, bar):
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject.upperLimit*0.99
            shortExecute = self.tickObject.lowerLimit*1.01
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
            self.buyOpen(symbol, buyExecute, volume)

    def shortCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        if self.orderDict[symbol + '_OPEN']:
            self.writeCtaLog('haveOpenOrder_Pass')
        else:
            self.shortOpen(symbol, shortExecute, volume)

    def coverCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        cancelled,canceling = self.cancelCloseOrder(bar)
        if cancelled:
            self.coverClose(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
        else:
            self.toExcuteOrdersID += 1
            self.toExcuteOrders[self.toExcuteOrdersID] = {
                "symbol": symbol,
                "price": buyExecute,
                "volume": self.ownPosDict[symbol + "_SHORT"],
                "orderType": "coverClose",
                "canceling":canceling
            }

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        cancelled,canceling = self.cancelCloseOrder(bar)
        if cancelled:
            self.sellClose(symbol, shortExecute, self.ownPosDict[symbol + '_LONG'])
        else:
            self.toExcuteOrdersID += 1
            self.toExcuteOrders[self.toExcuteOrdersID] = {
                "symbol": symbol,
                "price": shortExecute,
                "volume": self.ownPosDict[symbol + '_LONG'],
                "orderType": "sellClose",
                "canceling": canceling
            }

    def shortOpen(self, symbol, price, volume):
        shortOpenOrderList = self.short(symbol, price, volume)
        self.orderDict[symbol + '_OPEN'].extend(shortOpenOrderList)

    def buyOpen(self, symbol, price, volume):
        buyOpenOrderList = self.buy(symbol, price, volume)
        self.orderDict[symbol + '_OPEN'].extend(buyOpenOrderList)

    def sellClose(self, symbol, price, volume):
        sellCloseOrderList = self.sell(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def coverClose(self, symbol, price, volume):
        coverCloseOrderList = self.cover(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)


# executeManagement--------------------------------------------------------
    def on5sBar(self, bar):
    # def onBar(self, bar):
        self.writeCtaLog('adxKdjBtcStrategy####5S####ownposDict:%s####'%(self.ownPosDict))
        SL = self.onBarRiskControl(bar)
        if not SL:
            EX = self.onBarExit(bar)
            if not EX:
                self.onBarExecute(bar)
        self.onBarPosition(bar)


    def onBarExit(self, bar):
        Exit = False
        symbol = bar.vtSymbol
        am30 = self.getArrayManager(symbol, "30m")

        if not am30.inited:
            return

        adxTrend = ta.ADX(am30.high, am30.low, am30.close, self.adxPeriod)

        # Status
        if (adxTrend[-1]>self.adxExitThreshold):
            if self.ownPosDict[symbol + "_LONG"] > 0 :
                self.sellCheckExtend(bar)
                Exit = True
            if self.ownPosDict[symbol + "_SHORT"] > 0:
                self.coverCheckExtend(bar)
                Exit = True
        return Exit

    def onBarRiskControl(self, bar):
        symbol = bar.vtSymbol
        stopLoss = False
        if self.ownPosDict[symbol + "_LONG"] == 0 and self.ownPosDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict = 0
            self.intraTradeLowDict = 999999
            self.longStop = 0
            self.shortStop = 999999
            self.nChange = 0

        # 持有多头仓位
        elif self.ownPosDict[symbol + "_LONG"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeHighDict = max(self.intraTradeHighDict, bar.high)
            self.nChange = (self.intraTradeHighDict/firstOrder-1)//self.trailingPct
            changePrice = firstOrder*self.nChange*self.trailingPct
            self.longStop = max(self.longStop, firstOrder*(1-self.trailingPct)+changePrice)
            if bar.low <= self.longStop*1.005:
                self.sellCheckExtend(bar)
                stopLoss = True
            self.writeCtaLog('longStop%s'%(self.longStop))
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeLowDict = min(self.intraTradeLowDict, bar.low)
            self.nChange = -1* (self.intraTradeLowDict/firstOrder-1)//self.trailingPct
            changePrice = firstOrder*self.nChange*self.trailingPct
            self.shortStop = min(self.shortStop, firstOrder*(1+self.trailingPct)-changePrice)
            if bar.high >= self.shortStop*0.995:
                self.coverCheckExtend(bar)
                stopLoss = True
            self.writeCtaLog('shortStop%s'%(self.shortStop))
        return stopLoss

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if (self.adxCanTrade == 1):
            if (self.priceDirection == 1) and (self.ownPosDict[symbol + "_LONG"] == 0):
                if (self.ownPosDict[symbol + "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)

            elif (self.priceDirection == -1) and (self.ownPosDict[symbol + "_SHORT"] == 0):
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
            self.nPos=0
        elif (self.ownPosDict[symbol+'_LONG']>0 and self.nPos < 1):
            if (firstOrder/bar.close-1) >= self.addPct:
                self.nPos += 1
                self.buyCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))
        elif (self.ownPosDict[symbol + "_SHORT"] > 0 and self.nPos < 1):
            if (bar.close/firstOrder-1) >= self.addPct:
                self.nPos += 1
                self.shortCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))


    # ----------------------------------------------------------------------
    def on30MinBar(self, bar):
        symbol = bar.vtSymbol

        am30 = self.getArrayManager(symbol, "30m")

        if not am30.inited:
            return

        adxTrend = ta.ADX(am30.high, am30.low, am30.close, self.adxPeriod)

        # Status
        if (adxTrend[-1]<=self.adxEntryThreshold):
            self.adxCanTrade = 1
        else:
            self.adxCanTrade = -1

        self.writeCtaLog('adxTrend: %s, adxCanTrade: %s:'%(adxTrend[-1], self.adxCanTrade))

    def on15MinBar(self, bar):
        symbol = bar.vtSymbol

        am15 = self.getArrayManager(symbol, "15m")

        if not am15.inited:
            return

        k, d = ta.STOCH(am15.high, am15.low, am15.close, self.fastkPeriod, \
                     self.slowkPeriod, self.slowkMaType, \
                     self.slowdPeriod, self.slowdMaType)

        kdUp = (k[-1]<=self.overBought) and (k[-1]>k[-3]) and (k[-1]>d[-1])
        kdDn = (k[-1]>=self.overSold) and (k[-1]<k[-3]) and (k[-1]<d[-1])

        if kdUp:
            self.priceDirection = 1
        elif kdDn:
            self.priceDirection = -1
        else:
            self.priceDirection = 0

#         self.writeCtaLog(u'macd: %s, macdSignal: %s, priceDirection: %s'%(macd[-3:], macdSignal[-1], self.priceDirection))
        self.putEvent()



    # ----------------------------------------------------------------------
    def dealtoExcuteOrders(self, symbol):
        for ID in list(self.toExcuteOrders):
            order = self.toExcuteOrders[ID]
            if order["orderType"] in ["coverClose", "sellClose"]:
                # 前置要求中待撤销的订单已从orderDict中全部撤销
                if len(set(order["canceling"]) & set(self.orderDict[symbol + '_CLOSE'])) == 0:
                    if order["orderType"] == "coverClose":
                        self.coverClose(order["symbol"], order["price"], order["volume"])
                    elif order["orderType"] == "sellClose":
                        self.sellClose(order["symbol"], order["price"], order["volume"])
                    # 清除该待执行订单
                    del self.toExcuteOrders[ID]


    def on5MinBar(self, bar):
        pass
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        symbol = order.vtSymbol
        self.onOrderEmail(order)
        if order.status in STATUS_FINISHED:
            if (order.offset == OFFSET_OPEN) and (str(order.vtOrderID) in self.orderDict[symbol + '_OPEN']):
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif (order.offset == OFFSET_CLOSE) and (str(order.vtOrderID) in self.orderDict[symbol + '_CLOSE']):
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))
        # 触发撤单成功,扫描待执行订单的前置撤单要求是否达到，达到则触发对待执行订单的发单
        if order.status == STATUS_CANCELLED:
            self.dealtoExcuteOrders(symbol)

    def onOrderEmail(self, order):
        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
        if order.thisTradedVolume != 0:
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s'\
                        %(trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol+'%s'%(self.nPos)] = trade.price
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime = trade.tradeDatetime
        self.onTradeOwnPosDict(trade)
        self.takeProfit(trade)

    def onTradeOwnPosDict(self, trade):
        symbol = trade.vtSymbol
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)

    def takeProfit(self, trade):
        symbol = trade.vtSymbol
        firstOrder = self.transactionPrice[symbol+'0']
        longFirstProfit = firstOrder*(1+self.takeProfitFirstPct)
        longSecondProfit = firstOrder*(1+self.takeProfitSecondPct)
        shortFirstProfit = firstOrder*(1-self.takeProfitFirstPct)
        shortSecondProfit = firstOrder*(1-self.takeProfitSecondPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellClose(symbol, longFirstProfit, trade.volume//2)
                self.sellClose(symbol, longSecondProfit, trade.volume-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.coverClose(symbol, shortFirstProfit, trade.volume//2)
                self.coverClose(symbol, shortSecondProfit,trade.volume-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass