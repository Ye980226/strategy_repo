### ARPSYMa
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import pandas as pd
import numpy as np
from datetime import timedelta, datetime
import time

########################################################################
# 策略继承CtaTemplate
class ARPSYMaStrategy(CtaTemplate):
    """ARPSY均线策略Demo"""
    className = 'ARPSYMaStrategy'
    author = 'Chenziyue'

    # 策略参数
    fastPeriod = 15 ; slowPeriod = 36 ; timePeriod = 10
    arPeriod = 15 ; psyPeriod = 12
    multiplier = 5 ; upperthreshold = 0.55 ; lowerthreshold = 0.35
    lot = 1 ; allLot = 5 ; barPeriod = 150

    # 风控参数
    stopControlTime = 6; holdHour = 25;expectReturn = 0.001
    trailingPct = 0.035; takeProfitFirstPct = 0.06

    # 策略变量
    maTrend = {}
    transactionPrice = {}; openTime = {}; closeTime = {}
    rest_lot = {}
    longStop = {};longProfit = {};shortStop = {};shortProfit = {}
    # 自维护仓位与订单
    ownPosDict = {};orderDict = {}


    # 参数列表
    paramList = ['fastPeriod','slowPeriod','timePeriod',
                 'arPeriod','psyPeriod',
                 'multiplier', 'upperthreshold','lowerthreshold',
                 'trailingPct','takeProfitFirstPct',
                 'lot', 'allLot']
    # 变量列表
    varList = ['maTrend',
               'transactionPrice']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['ownPosDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super().__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        # signalVar
        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.maTrend = {s: 0 for s in self.symbolList}
        self.signalCross = {s: 0 for s in self.symbolList}

        # riskControlVar
        self.closeTime = {s: None for s in self.symbolList}
        self.openTime = {s: None for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}  # 生成成交价格的字典
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}
        self.nChange = {s: 0 for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}
        self.rest_lot = {s: 0 for s in self.symbolList}

        # posManage
        nPos = {s: 0 for s in self.symbolList}
        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
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
        engineType = self.getEngineType()
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


    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送"""
        self.writeCtaLog('ARPSYMaStrategy####5S####ownPosDict:%s####' % (self.ownPosDict))
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)   
        
    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        if (self.signalCross[symbol]==1) and (self.maTrend[symbol] == 1) and (self.ownPosDict[symbol + '_LONG']<self.allLot):
            if self.stopLossControl[symbol] == -1:
                self.stopLossControl[symbol] = 0
            if self.stopLossControl[symbol] == 0:
                if (self.ownPosDict[symbol + '_SHORT'] == 0):
                    self.buyCheckExtend(bar)
                elif (self.ownPosDict[symbol + '_SHORT'] > 0):
                    self.coverCheckExtend(bar)
                    self.writeCtaLog('coverBeforeBuy')
                    self.buyCheckExtend(bar)

        elif (self.signalCross[symbol]==-1) and (self.maTrend[symbol] == -1) and (self.ownPosDict[symbol + '_SHORT']<self.allLot):
            if self.stopLossControl[symbol] == 1:
                self.stopLossControl[symbol] = 0
            if self.stopLossControl[symbol] == 0:
                if (self.ownPosDict[symbol + '_LONG'] == 0):
                    self.shortCheckExtend(bar)
                elif (self.ownPosDict[symbol + '_LONG'] > 0):
                    self.sellCheckExtend(bar)
                    self.writeCtaLog('sellBeforeShort')
                    self.shortCheckExtend(bar)

#             self.rest_lot[symbol] = self.allLot - self.ownPosDict[symbol + '_SHORT']
    # ----------------------------------------------------------------------
    def checkHoldTime(self, bar):
        symbol = bar.vtSymbol
        if self.openTime[symbol]:
            longUnexpect = (bar.close / self.transactionPrice[symbol] - 1) < self.expectReturn
            shortUnexpect = (self.transactionPrice[symbol] / bar.close - 1) < self.expectReturn
            if ((bar.datetime - self.openTime[symbol]) >= timedelta(hours=self.holdHour)):
                if (self.ownPosDict[symbol + "_LONG"] > 0) and longUnexpect:
                    self.sellCheckExtend(bar)
                    self.writeCtaLog('longUnexpect_Sell')
                    self.openTime[symbol] = None
                elif (self.ownPosDict[symbol + "_SHORT"] > 0) and shortUnexpect:
                    self.coverCheckExtend(bar)
                    self.writeCtaLog('shortUnexpect_Cover')
                    self.openTime[symbol] = None

    def onBarStopLoss(self, bar):
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
            self.nChange[symbol] = (self.intraTradeHighDict[symbol] / self.transactionPrice[symbol] - 1)//self.trailingPct
            changePrice = self.transactionPrice[symbol] * self.nChange[symbol] * self.trailingPct
            self.longStop[symbol] = max(self.longStop[symbol],
                                        self.transactionPrice[symbol] * (1 - self.trailingPct) + changePrice)
            if bar.low <= self.longStop[symbol]:
                self.sellCheckExtend(bar)
                self.writeCtaLog('sellTrailingStop')
            else:
                self.checkHoldTime(bar)
            self.writeCtaLog('longStop%s' % (self.longStop[symbol]))
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.nChange[symbol] = -1 * (self.intraTradeLowDict[symbol] / self.transactionPrice[symbol] - 1)//self.trailingPct
            changePrice = self.transactionPrice[symbol] * self.nChange[symbol] * self.trailingPct
            self.shortStop[symbol] = min(self.shortStop[symbol],
                                         self.transactionPrice[symbol] * (1 + self.trailingPct) - changePrice)
            if bar.high >= self.shortStop[symbol]:
                self.coverCheckExtend(bar)
                self.writeCtaLog('coverTrailingStop')
            else:
                self.checkHoldTime(bar)
            self.writeCtaLog('shortStop%s' % (self.shortStop[symbol]))
        self.putEvent()
    # ----------------------------------------------------------------------

    def calculate(self, factor, t):
        mas = ta.MA(factor, t)
        mal = ta.MA(factor, self.multiplier * t)
        df = np.vstack((mas, mal))
        scoretable = np.array(list(map(lambda s, l: 1 if s > l else 0, df[0, :], df[1, :])))
        return scoretable

    def on60MinBar(self, bar):
        """收到60分钟Bar推送"""
        symbol = bar.vtSymbol
        am60 = self.getArrayManager(symbol, "60m")  # 获取历史数组
        if not am60.inited:
            return
        # 计算均线并判断趋势-------------------------------------------------
        fastMa = ta.MA(am60.close, self.fastPeriod)
        slowMa = ta.MA(am60.close, self.slowPeriod)

        if (fastMa[-1] > slowMa[-1]):
            self.maTrend[symbol] = 1
        elif (fastMa[-1] <= slowMa[-1]):
            self.maTrend[symbol] = -1

        # 计算策略需要的信号-------------------------------------------------

        ar = ta.SUM(am60.high[1:] - am60.open[1:], self.arPeriod) / ta.SUM(am60.open[1:] - am60.low[1:], self.arPeriod)
        x = range(1, self.timePeriod + 1, 1)
        arscore = np.array([self.calculate(ar, t) for t in x]).transpose().sum(axis=1)

        psy = ta.SUM(np.array(am60.close[1:] > am60.close[:-1], dtype='double'), self.psyPeriod) / self.psyPeriod
        psyscore = np.array([self.calculate(psy, t) for t in x]).transpose().sum(axis=1)
        score = arscore + psyscore
        upThreshold = 2 * self.timePeriod * self.upperthreshold
        lowThreshold =  2 * self.timePeriod * self.lowerthreshold

        if (score[-1] > upThreshold) and (score[-2] < upThreshold):
            self.signalCross[symbol] = 1
        elif (score[-1] <lowThreshold) and (score[-2] > lowThreshold):
            self.signalCross[symbol] = -1
        else:
            self.signalCross[symbol] = 0
        self.writeCtaLog(u'on1MinBar,datetime:%s,signalCross:%s,maTrend:%s,rest_lot:%s'
                         % (bar.datetime, self.signalCross[symbol], self.maTrend[symbol],self.rest_lot[symbol]))
        self.putEvent()

    # ----------------------------------------------------------------------
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
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s' % \
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

        if order.status in STATUS_FINISHED:
            if order.offset == OFFSET_OPEN:
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif order.offset == OFFSET_CLOSE:
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送"""
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s' \
                         % (trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        self.writeCtaLog('Quarter####ARPSYMaStrategy:%s' % (symbol))

        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
            self.openTime[symbol] = trade.tradeDatetime
            self.closeTime[symbol] = None
        elif trade.offset == OFFSET_CLOSE:
            self.openTime[symbol] = None
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

        longProfit = self.transactionPrice[symbol] * (1 + self.takeProfitFirstPct)
        shortProfit = self.transactionPrice[symbol] * (1 - self.takeProfitFirstPct)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.cancelCloseOrder(trade)
                self.sellTakeProfitOrder(trade,longProfit,trade.volume)
                self.writeCtaLog('long### tp1:%s' %longProfit)
            elif trade.direction == DIRECTION_SHORT:
                self.cancelCloseOrder(trade)
                self.coverTakeProfitOrder(trade,shortProfit, trade.volume)
                self.writeCtaLog('short### tp1:%s' %shortProfit)

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass