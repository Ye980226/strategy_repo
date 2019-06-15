from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time

########################################################################
class maCrsiEosStrategy(CtaTemplate):
    className = 'maCrsiEosStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 300
    adxPeriod = 10; adxMaxPeriod = 20; adxThreshold = 35
    maPeriod = 60; maType = 0
    rsiPeriod = 10; rsiMaPeriod=5
    crsiLowThreshold = 40; crsiHighThreshold=60

    # 风控参数
    stopLossPct = 0.045; protectPct=0.03
    takeProfitFirstPct = 0.05; takeProfitSecondPct = 0.09
#     stopControlTime = 2
    lot = 800

    # 仓位管理参数
    addPct = 0.025; addMultipler = 1.6

    # 信号变量
    maTrend = 0; crsiRevert = 0
    adxCanTrade = 0
    stopLossControl = 0

    transactionPrice = {}

    # 自维护仓位与订单
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'adxPeriod', 'adxMaxPeriod','adxThreshold',
                 'maPeriod', 'maType',
                 'rsiPeriod','rsiMaPeriod',
                 'crsiLowThreshold', 'crsiHighThreshold',
                 'stopControlTime','stopLossPct','protectPct',
                 'takeProfitFirstPct', 'takeProfitSecondPct',
                 'addPct', 'addMultipler', 'lot',
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'maTrend', 'crsiRevert',
#               'filterCanTrade',
               'transactionPrice',
#                'stopLossControl'
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
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.closeTime = None
        self.openTime = None
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
#     def on5sBar(self, bar):
    def onBar(self, bar):
        self.writeCtaLog('maCrsiEosStrategy####5S####ownposDict:%s####'%(self.ownPosDict))
#         self.onBarExitTimeControl(bar)
        self.onBarExecute(bar)
        self.protectStopLoss(bar)
#         self.onBarPosition(bar)
#         self.onBarExit(bar)

    def onBarExit(self, bar):
        symbol = bar.vtSymbol
        if (self.posDict[symbol + '_LONG'] > 0) and (self.maTrend==-1):
            self.sellCheckExtend(bar)
        elif (self.posDict[symbol + '_SHORT'] > 0) and (self.maTrend==1):
            self.coverCheckExtend(bar)

    def onBarExitTimeControl(self, bar):
        if self.closeTime:
            if (bar.datetime - self.closeTime) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl = 0

    def protectStopLoss(self, bar):
        # 计算止损止盈价位
        symbol = bar.vtSymbol
        orderPrice = self.transactionPrice[symbol]
        longStopLossPrice =  orderPrice* (1-self.stopLossPct)
        shortStopLossPrice = orderPrice * (1 + self.stopLossPct)
        longProtectStopPrice = orderPrice*(1+self.protectPct)
        shortProtectStopPrice = orderPrice*(1-self.protectPct)

        if (self.posDict[symbol + '_LONG'] == 0) and (self.posDict[symbol + '_SHORT'] == 0):
            self.stopProtect = 0
        elif (self.posDict[symbol + '_LONG'] > 0):
            if (bar.close)>= longProtectStopPrice:
                self.stopProtect = 1
            if (self.stopProtect== 1) and (bar.low <= (1.003 * self.transactionPrice[symbol])):
                self.sellCheckExtend(bar)
                self.stopProtect = 0
            elif (self.stopProtect == 0) and (bar.low <= longStopLossPrice):
                self.sellCheckExtend(bar)
        elif (self.posDict[symbol + '_SHORT'] > 0):
            if bar.close <= shortProtectStopPrice:
                self.stopProtect= -1
            if (self.stopProtect == -1) and (bar.high >= (0.997 * self.transactionPrice[symbol])):
                self.coverCheckExtend(bar)
                self.stopProtect = 0
            elif (self.stopProtect == 0) and (bar.high >= shortStopLossPrice):
                self.coverCheckExtend(bar)
        else:
            self.onBarExit(bar)

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if self.adxCanTrade==1:
            if (self.maTrend == 1) and (self.crsiRevert == 1) and (self.ownPosDict[symbol + "_LONG"] == 0):
                if (self.ownPosDict[symbol + "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)
            elif (self.maTrend == -1) and (self.crsiRevert == -1) and (self.ownPosDict[symbol + "_SHORT"] == 0):
                if (self.ownPosDict[symbol + "_LONG"] == 0):
                    self.shortCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_LONG"] > 0):
                    self.sellCheckExtend(bar)
                    self.shortCheckExtend(bar)
        self.putEvent()

    def onBarPosition(self,bar):
        symbol = bar.vtSymbol
        firstOrder=self.transactionPrice[symbol]
        if (self.ownPosDict[symbol+'_LONG']==0) and (self.ownPosDict[symbol + "_SHORT"]==0):
            self.nPos=0
        elif (self.ownPosDict[symbol+'_LONG']>0 and self.nPos < 1):
            if (bar.close/firstOrder-1) >= self.addPct:
                self.nPos += 1
                self.buyCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))
        elif (self.ownPosDict[symbol + "_SHORT"] > 0 and self.nPos < 1):
            if (firstOrder/bar.close-1) >= self.addPct:
                self.nPos += 1
                self.shortCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))
        self.putEvent()
    # ----------------------------------------------------------------------
    def on30MinBar(self, bar):
        """30分钟K线推送"""
        symbol = bar.vtSymbol

        am30 = self.getArrayManager(symbol, "30m")

        if not am30.inited:
            return

        adxTrend = ta.ADX(am30.high, am30.low, am30.close, self.adxPeriod)
        adxMax = ta.MAX(adxTrend, self.adxMaxPeriod)

        # Status
        if ((adxMax[-1]>=self.adxThreshold) and (adxTrend[-1]<self.adxThreshold)) or (adxTrend[-1]<=10):
            self.adxCanTrade = -1
        else:
            self.adxCanTrade = 1

        self.writeCtaLog(u'adxTrend[-1]: %s ,adxMax[-1]: %s'%(adxTrend[-1], adxMax[-1]))

    def on15MinBar(self, bar):
        pass

    def on5MinBar(self, bar):
        symbol = bar.vtSymbol
        am5 = self.getArrayManager(symbol, "5m")
        am15 = self.getArrayManager(symbol, "15m")

        if not am5.inited:
            return
        maClose = ta.MA(am15.close, self.maPeriod, self.maType)
        # Status
        if (am15.close[-1]>maClose[-1]):
            self.maTrend = 1
        else:
            self.maTrend = -1

        crsi = ta.MA(ta.RSI(am5.close, self.rsiPeriod), self.rsiMaPeriod)
        if (crsi[-1]<=self.crsiLowThreshold) and (crsi[-1]>crsi[-3]):
            self.crsiRevert = 1
        elif (crsi[-1]>=self.crsiHighThreshold)and (crsi[-1]<crsi[-3]):
            self.crsiRevert = -1
        else:
            self.crsiRevert = 0
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
            self.transactionPrice[symbol] = trade.price
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime = trade.tradeDatetime
#             if trade.direction == DIRECTION_SHORT:
#                 self.stopLossControl = 1
#             elif trade.direction == DIRECTION_LONG:
#                 self.stopLossControl = -1
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
        self.writeCtaLog('tradeDatetime:%s, ownPosDict:%s'%(trade.tradeDatetime, self.ownPosDict))

    def takeProfit(self, trade):
        symbol = trade.vtSymbol
        firstOrder = self.transactionPrice[symbol]
        longFirstProfit = firstOrder*(1+self.takeProfitFirstPct)
        longSecondProfit = firstOrder*(1+self.takeProfitSecondPct)
        shortFirstProfit = firstOrder*(1-self.takeProfitFirstPct)
        shortSecondProfit = firstOrder*(1-self.takeProfitSecondPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellClose(symbol, longFirstProfit, 3*trade.volume//4)
                self.sellClose(symbol, longSecondProfit, trade.volume-3*trade.volume//4)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.coverClose(symbol, shortFirstProfit, 3*trade.volume//4)
                self.coverClose(symbol, shortSecondProfit, trade.volume-3*trade.volume//4)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))

    def onStopOrder(self, so):
        """停止单推送"""
        pass