from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time

########################################################################
class maSarStrategy(CtaTemplate):
    className = 'diAdxStairStrategy'
    author = 'ChannelCMT'

    # 策略参数
    barPeriod = 300
    maPeriod = 280; maType = 0
    sarAcceleration = 0.006
    volPeriod = 50; lowVolThrehold = 0.002

    # 风控参数
    stopControlTime = 2
    lot = 2

    # 仓位管理参数
    addPct = 0.03; addMultipler = 2

    # 信号变量
    maTrend = 0; priceDirection = 0
    stopLossControl = 0
    filterCanTrade = 0

    transactionPrice = {}

    # 自维护仓位与订单
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'symbolList',
                 'maPeriod', 'maType',
                 'sarAcceleration',
                 'volPeriod',
                 'lowVolThrehold',
                 'stopControlTime',
                 'addPct','addMultipler','lot',
                 ]

    # 变量列表，保存了变量的名称
    varList = ['ownPosDict',
               'maTrend', 'priceDirection','filterCanTrade',
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
        self.openTime = None
        self.longStop = 0
        self.shortStop = 999999
        self.intraTradeHighDict = 0
        self.intraTradeLowDict = 999999

        # posManage
        self.nPos = 0

        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.ownEveningDict = {s + '_LONG': 0, s + '_SHORT': 0}
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
        self.cancelCloseOrder(bar)
        if self.ownEveningDict[symbol + '_SHORT']==self.ownPosDict[symbol + '_SHORT']:
            coverCloseOrderList = self.cover(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
            self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)
        if self.ownEveningDict[symbol + '_LONG'] == self.ownPosDict[symbol + '_LONG']:
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
    def on5sBar(self, bar):
    # def onBar(self, bar):
        self.writeCtaLog('maSarEosStrategy####5S####ownposDict:%s####'%(self.ownPosDict))
        self.writeCtaLog('maSarEosStrategy####5S####ownEveningDict:%s####' % (self.ownEveningDict))
        self.onBarExitTimeControl(bar)
        self.lowVolFilter(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

    def lowVolFilter(self, bar):
        symbol = bar.vtSymbol
        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        std = ta.STDDEV(am5.close, self.volPeriod)
        atr = ta.ATR(am5.high, am5.low, am5.close, self.volPeriod)
        rangeHL = ta.MAX(am5.high, self.volPeriod)-ta.MIN(am5.low, self.volPeriod)
        minVol = min(std[-1], atr[-1], rangeHL[-1])
        lowFilterRange = am5.close[-1]*self.lowVolThrehold
        if (minVol >= lowFilterRange) :
            self.filterCanTrade = 1
        else:
            self.filterCanTrade = -1

        if self.filterCanTrade==-1:
            if (self.ownPosDict[symbol+'_LONG'] > 0):
                self.sellCheckExtend(bar)
            elif (self.ownPosDict[symbol+'_SHORT'] > 0):
                self.coverCheckExtend(bar)
        self.putEvent()
    def onBarExitTimeControl(self, bar):
        if self.closeTime:
            if (bar.datetime - self.closeTime) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl = 0

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if (self.filterCanTrade==1) and (self.stopLossControl == 0):
            if (self.maTrend == 1) and (self.priceDirection == 1) and (self.ownPosDict[symbol + "_LONG"] == 0):
                if (self.ownPosDict[symbol + "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol + "_SHORT"] > 0):
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)
            elif (self.maTrend == -1) and (self.priceDirection == -1) and (self.ownPosDict[symbol + "_SHORT"] == 0):
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
            if (bar.close/firstOrder-1) >= self.addPct:
                self.nPos += 1
                self.buyCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))
        elif (self.ownPosDict[symbol + "_SHORT"] > 0 and self.nPos < 1):
            if (firstOrder/bar.close-1) >= self.addPct:
                self.nPos += 1
                self.shortCheckExtend(bar, int(self.lot*(self.addMultipler**self.nPos)))
        self.putEvent()
    # ----------------------------------------------------------------------
    def on5MinBar(self, bar):
        symbol = bar.vtSymbol
        am5 = self.getArrayManager(symbol, "5m")

        if not am5.inited:
            return

        maClose = ta.MA(am5.close, self.maPeriod, self.maType)

        # Status
        if (am5.close[-1]>maClose[-1]):
            self.maTrend = 1
        else:
            self.maTrend = -1

        sar = ta.SAR(am5.high, am5.low, self.sarAcceleration)
        if (am5.close[-1]>sar[-1]) and (am5.close[-2]<sar[-2]):
            self.priceDirection = 1
        elif (am5.close[-1]<sar[-1]) and (am5.close[-2]>sar[-2]):
            self.priceDirection = -1
        else:
            self.priceDirection = 0
        self.writeCtaLog('am5.close:%s, SAR: %s'%(am5.close[-2:], sar[-2:]))
        self.putEvent()
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        symbol = order.vtSymbol
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

        # ownEveningDict
        if order.status == STATUS_CANCELLED:
            if order.direction == DIRECTION_SHORT and order.offset == OFFSET_CLOSE:
                self.ownEveningDict[symbol + '_LONG'] += int(order.totalVolume)
            elif order.direction == DIRECTION_LONG and order.offset == OFFSET_CLOSE:
                self.ownEveningDict[symbol + '_SHORT'] += int(order.totalVolume)
        elif order.status == STATUS_NOTTRADED:
            if order.direction == DIRECTION_SHORT and order.offset == OFFSET_CLOSE:
                self.ownEveningDict[symbol + '_LONG'] -= int(order.totalVolume)
            elif order.direction == DIRECTION_LONG and order.offset == OFFSET_CLOSE:
                self.ownEveningDict[symbol + '_SHORT'] -= int(order.totalVolume)


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

        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol+'%s'%self.nPos] = trade.price
            self.openTime = trade.tradeTime
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime = trade.tradeDatetime
            self.openTime = None
            if trade.direction == DIRECTION_SHORT:
                self.stopLossControl = 1
            elif trade.direction == DIRECTION_LONG:
                self.stopLossControl = -1

        # ownPosDict
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)
            self.ownEveningDict[symbol + '_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
            self.ownEveningDict[symbol + '_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)
        self.writeCtaLog('tradeDatetime:%s, ownPosDict:%s'%(trade.tradeDatetime, self.ownPosDict))
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass