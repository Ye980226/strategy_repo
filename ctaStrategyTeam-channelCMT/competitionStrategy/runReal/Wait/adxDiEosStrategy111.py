from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time

########################################################################
class diAdxStairStrategy(CtaTemplate):
    className = 'diAdxStairStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 200
    adxPeriod = 20; adxMaPeriod = 24; adxMaType = 2; adxThreshold = 19
    diPeriod = 25
    signalMaPeriod = 70; signalMaType = 0

    # 风控参数
    trailingPct = 0.025; stopControlTime = 4
    takeProfitFirstPct = 0.055; takeProfitSecondPct = 0.075
    lot = 500

    # 仓位管理参数
    addPct = 0.005; addMultipler = 1

    # 策略变量
    adxUp = 0; priceDirection = 0; signalMaDirection = 0
    transactionPrice = {}


    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'adxPeriod', 'adxMaPeriod', 'adxMaType', 'adxThreshold',
                 'diPeriod','signalMaPeriod', 'signalMaType',
                 'trailingPct', 'stopControlTime',
                 'addPct','addMultipler','lot',
                 'takeProfitFirstPct','takeProfitSecondPct'
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'adxUp', 'priceDirection', 'signalMaDirection',
               'transactionPrice'
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
        self.adxUp = 0
        self.priceDirection = 0
        self.signalMaDirection = 0

        # riskControlVar
        self.transactionPrice = {s+'0': 0 for s in self.symbolList}
        self.closeTime = None
        self.stopLossControl = 0
        self.longStop = 0
        self.shortStop = 999999
        self.intraTradeHighDict = 0
        self.intraTradeLowDict = 999999

        # posManage
        self.nPos = 0

        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}
        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'adx60策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'adx60策略停止')
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

    def timeSleep(self):
        engineType = self.getEngineType()
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

    def priceExecute(self, bar):
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject.upperLimit * 0.99
            shortExecute = self.tickObject.lowerLimit * 1.01
        else:
            buyExecute = bar.close * 1.02
            shortExecute = bar.close * 0.98
        return buyExecute, shortExecute

    def buyCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        # 002CorrectCheckOpenOrder################################################
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
        # 002CorrectCheckOpenOrder################################################
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
#####################################
    # def on5sBar(self, bar):
    def onBar(self, bar):
        self.writeCtaLog('diAdxStairStrategy####5S####posDict:%s####'%(self.ownPosDict))
        self.onBarExit(bar)
        self.onBarExitTimeControl(bar)
        self.onBarRiskControl(bar)
        self.onBarPosition(bar)
        self.onBarExecute(bar)

    def onBarExitTimeControl(self, bar):
        if self.closeTime:
            if (bar.datetime - self.closeTime) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl = 0

    def onBarRiskControl(self, bar):
        symbol = bar.vtSymbol
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
            if bar.low <= self.longStop:
                self.sellCheckExtend(bar)
            self.writeCtaLog('longStop%s'%(self.longStop))
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeLowDict = min(self.intraTradeLowDict, bar.low)
            self.nChange = -1* (self.intraTradeLowDict/firstOrder-1)//self.trailingPct
            changePrice = firstOrder*self.nChange*self.trailingPct
            self.shortStop = min(self.shortStop, firstOrder*(1+self.trailingPct)-changePrice)
            if bar.high >= self.shortStop:
                self.coverCheckExtend(bar)
            self.writeCtaLog('shortStop%s'%(self.shortStop))

    def onBarExit(self, bar):
        symbol = bar.vtSymbol
        if (self.adxUp == -1):
            if (self.ownPosDict[symbol + "_LONG"] > 0) :
                self.sellCheckExtend(bar)
            if self.ownPosDict[symbol + "_SHORT"] > 0:
                self.coverCheckExtend(bar)

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

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if (self.adxUp == 1):
            if (self.priceDirection == 1) and (self.signalMaDirection==1) \
            and (self.ownPosDict[symbol + "_LONG"] == 0):
                if self.stopLossControl == -1:
                    self.stopLossControl = 0
                if (self.stopLossControl == 0):
                    if (self.ownPosDict[symbol + "_SHORT"] == 0):
                        self.buyCheckExtend(bar)
                    elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                        self.coverCheckExtend(bar)
                        self.buyCheckExtend(bar)

            elif (self.priceDirection == -1) and (self.signalMaDirection==-1)\
            and (self.ownPosDict[symbol + "_SHORT"] == 0):
                if self.stopLossControl == 1:
                    self.stopLossControl = 0
                if (self.stopLossControl == 0):
                    if (self.ownPosDict[symbol + "_LONG"] == 0):
                        self.shortCheckExtend(bar)
                    elif (self.ownPosDict[symbol + "_LONG"] > 0):
                        self.sellCheckExtend(bar)
                        self.shortCheckExtend(bar)
        self.putEvent()

    # ----------------------------------------------------------------------
    def on60MinBar(self, bar):
        symbol = bar.vtSymbol

        am60 = self.getArrayManager(symbol, "60m")

        if not am60.inited:
            return

        adxTrend = ta.ADX(am60.high, am60.low, am60.close, self.adxPeriod)
        adxMa = ta.MA(adxTrend, self.adxMaPeriod, matype=self.adxMaType)

        # Status
        if (adxTrend[-1] > adxMa[-1]) and (adxTrend[-1]>=self.adxThreshold):
            self.adxUp = 1
        else:
            self.adxUp = -1

        self.writeCtaLog(u'adxTrend[-1]: %s ,adxMa[-1]: %s'%(adxTrend[-1], adxMa[-1]))

        plusDi = ta.PLUS_DI(am60.high, am60.low, am60.close, self.diPeriod)
        minusDi = ta.MINUS_DI(am60.high, am60.low, am60.close, self.diPeriod)

        if (plusDi[-1]>minusDi[-1]):
            self.priceDirection = 1
        else:
            self.priceDirection = -1

        self.writeCtaLog(u'plusDi[-1]: %s ,minusDi[-1]: %s'%(plusDi[-1],minusDi[-1]))
        self.putEvent()
    def on5MinBar(self, bar):
        symbol = bar.vtSymbol

        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        # signal
        signalMa = ta.MA(am5.close, self.signalMaPeriod, matype=self.signalMaType)

        if signalMa[-1]>signalMa[-3]:
            self.signalMaDirection = 1
        elif signalMa[-1]<signalMa[-3]:
            self.signalMaDirection = -1
        else:
            self.signalMaDirection = 0
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
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s'\
                        %(trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        self.writeCtaLog('Quarter####diAdxStairStrategy:%s'%(symbol))
        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol+'%s'%self.nPos] = trade.price
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime = trade.tradeDatetime
            if trade.direction == DIRECTION_SHORT:
                self.stopLossControl = 1
            elif trade.direction == DIRECTION_LONG:
                self.stopLossControl = -1
        # ownPosDict
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)
        self.takeProfit(trade)

        print(trade.tradeTime, self.ownPosDict)

    def takeProfit(self, trade):
        # 发送止盈单
        symbol = trade.vtSymbol
        firstOrder = self.transactionPrice[symbol+'0']
        longFirstProfit = firstOrder*(1+self.takeProfitFirstPct)
        longSecondProfit = firstOrder*(1+self.takeProfitSecondPct)
        shortFirstProfit = firstOrder*(1-self.takeProfitFirstPct)
        shortSecondProfit = firstOrder*(1-self.takeProfitSecondPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellTakeProfitOrder(trade, longFirstProfit, trade.volume//2)
                self.sellTakeProfitOrder(trade, longSecondProfit, trade.volume-trade.volume//2)
                self.writeCtaLog('long### tp1:%s, tp2:%s'%(longFirstProfit, longSecondProfit))
            elif trade.direction == DIRECTION_SHORT:
                self.coverTakeProfitOrder(trade, shortFirstProfit, trade.volume//2)
                self.coverTakeProfitOrder(trade, shortSecondProfit,trade.volume-trade.volume//2)
                self.writeCtaLog('short### tp1:%s, tp2:%s'%(shortFirstProfit, shortSecondProfit))
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass