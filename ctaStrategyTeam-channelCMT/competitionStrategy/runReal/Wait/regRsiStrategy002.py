from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
from datetime import datetime, timedelta
import time
########################################################################
class regRsiStrategy(CtaTemplate):
    className = 'regRsiStrategy'
    author = 'ChannelCMT'
    # 策略参数

    barPeriod = 200
    regPeriod = 25; residualSmaPeriod = 20; residualLmaPeriod = 80
    rsiPeriod = 30; rsiMaPeriod = 5; rsiBBandPeriod = 10; unusualHour = 6
    rsiMinMaxPeriod = 15
    overBought = 80; overSold = 10
    atrPeriod = 40; atrMultipler = 5; profitMultiper = 2

    # 风控参数
    holdHour =8; expectReturn = 0.001

    # 仓位管理
    lot = 300
    addPct = 0.005; addMultiper = 1

    # 策略变量
    regTrend = {}; rsiBreakBand = {}; unusualStart = {}
    transactionPrice = {}; openTime={}
    intraTradeHighDict = {}; intraTradeLowDict = {}
    longStop = {}; shortStop = {}
    atrTrade = {}
    nPos = {}

    # 自维护字典
    ownPosDict = {}; orderDict = {}

    # 参数列表，保存了参数的名称
    paramList = [
                 'regPeriod','residualSmaPeriod','residualLmaPeriod',
                 'rsiPeriod', 'rsiMaPeriod','rsiBBandPeriod','unusualHour',
                 'rsiMinMaxPeriod',
                 'overBought', 'overSold', 'holdHour',
                 'atrMultipler', 'atrPeriod','profitMultiper',
                 'addPct','addMultiper',
                 'lot'
                ]

    # 变量列表，保存了变量的名称
    varList = ['transactionPrice',
               'regTrend','rsiBreakBand','unusualStart',
               'transactionPrice','openTime',
               'atrTrade',
               'ownPosDict','orderDict',
               'nPos']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        # 进场信号
        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.regTrend = {s: 0 for s in self.symbolList}
        self.rsiBreakBand = {s: 0 for s in self.symbolList}
        self.unusualStartTime = {s: None for s in self.symbolList}

        # 风险控制
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 999999 for s in self.symbolList}
        self.atrTrade = {s: 0 for s in self.symbolList}
        self.openTime = {s: None for s in self.symbolList}
        self.transactionPrice = {s+'0': 0 for s in self.symbolList}
        self.nPos = {s: 0 for s in self.symbolList}

        # 自定义仓位订单字典
        for s in self.symbolList:
            self.ownPosDict = {s+'_LONG':0, s+'_SHORT':0}
            self.orderDict = {s+'_OPEN' : [], s+'_CLOSE' : []}

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

    def on5sBar(self, bar):
#     def onBar(self, bar):
        """收到Bar推送"""
        self.writeCtaLog('###5s###ownPosDict:%s###'%(self.ownPosDict))
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

#     def onBar(self, bar):
#         pass

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        am15 = self.getArrayManager(symbol, "15m")

        if (not am15.inited):
            return

        # indicator
        rsi = ta.RSI(am15.close, self.rsiPeriod)
        rsiMa = ta.MA(rsi, self.rsiMaPeriod)
        rsiMax = ta.MAX(rsiMa, self.rsiMinMaxPeriod)
        rsiMin = ta.MIN(rsiMa, self.rsiMinMaxPeriod)

        # condition
        rsiBreakMax = (rsi[-1]>rsiMax[-2]) and (rsi[-2]<=rsiMax[-2])
        rsiBreakMin = (rsi[-1]<rsiMin[-2]) and (rsi[-2]>=rsiMin[-2])
        overBoughtDn = (rsi[-1]>self.overBought) and (rsiMax[-1]<rsiMax[-2])
        overSoldUp = (rsi[-1]<self.overSold) and (rsiMin[-1]>rsiMin[-2])

        atr = ta.ATR(am15.high, am15.low, am15.close, self.atrPeriod)[-1]

        # order
        if (rsiBreakMax) and (self.rsiBreakBand[symbol] == -1)\
        and (self.regTrend[symbol] == 1) and (self.ownPosDict[symbol+'_LONG']==0):
            if  (self.ownPosDict[symbol+'_SHORT']==0):
                self.buyCheckExtend(bar)  # 成交价*1.01发送高价位的限价单，以最优市价买入进场
                self.atrTrade[symbol] = atr
            elif (self.ownPosDict[symbol+'_SHORT'] > 0):
                self.coverCheckExtend(bar)
                self.buyCheckExtend(bar)
                self.atrTrade[symbol] = atr

        elif (rsiBreakMin) and (self.rsiBreakBand[symbol] == 1) \
        and (self.regTrend[symbol] == -1) and (self.ownPosDict[symbol + '_SHORT']==0):
            if (self.ownPosDict[symbol + '_LONG']==0) :
                self.shortCheckExtend(bar)
                self.atrTrade[symbol] = atr
            elif (self.ownPosDict[symbol + '_LONG']>0):
                self.sellCheckExtend(bar)
                self.shortCheckExtend(bar)
                self.atrTrade[symbol] = atr

        # exit
        if (self.regTrend[symbol]==-1) or overBoughtDn:
            if (self.ownPosDict[symbol+'_LONG']>0):
                self.sellCheckExtend(bar)
                print('signalLongExit')
        elif (self.regTrend[symbol]==1) or overSoldUp:
            if (self.ownPosDict[symbol+'_SHORT']>0):
                self.coverCheckExtend(bar)
                print('signalShortExit')


    def checkHoldTime(self, bar):
        symbol = bar.vtSymbol
        # holdTime
        if self.openTime[symbol]:
            firstOrder = self.transactionPrice[symbol+'0']
            longUnexpect = (bar.close/firstOrder-1)<self.expectReturn
            shortUnexpect = (firstOrder/bar.close-1)<self.expectReturn
            if ((bar.datetime-self.openTime[symbol])>=timedelta(hours=self.holdHour)):
                if (self.ownPosDict[symbol + "_LONG"] > 0) and longUnexpect:
                    self.sellCheckExtend(bar)
                    print('longUnexpect')
                    self.writeCtaLog('afterOpenOrder_Sell')
                    self.openTime[symbol] = None
                elif (self.ownPosDict[symbol + "_SHORT"] > 0) and shortUnexpect:
                    self.coverCheckExtend(bar)
                    print('shortUnexpect')
                    self.writeCtaLog('afterOpenOrder_Cover')
                    self.openTime[symbol] = None

    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
        am15 = self.getArrayManager(symbol, "15m")

        if (not am15.inited):
            return
        atr = ta.ATR(am15.high, am15.low, am15.close, self.atrPeriod)[-1]
        # 变量初始化
        if self.ownPosDict[symbol + "_LONG"] == 0 and self.ownPosDict[symbol + "_SHORT"] == 0:
            self.atrTrade[symbol] = 0
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
            self.longStop[symbol] = 0
            self.shortStop[symbol] = 999999
        # 持有多头仓位
        elif self.ownPosDict[symbol + "_LONG"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop[symbol] = max(self.longStop[symbol], self.intraTradeHighDict[symbol]-self.atrMultipler*atr)
            takeProfit = firstOrder+self.profitMultiper*self.atrMultipler*self.atrTrade[symbol]
            self.writeCtaLog('longStop:%s' % (self.longStop[symbol]))
            self.writeCtaLog('longTakeProfit:%s' % (takeProfit))
            if bar.low <= self.longStop[symbol]:
                self.sellCheckExtend(bar)
            elif bar.high> takeProfit:
                self.sellCheckExtend(bar)
            else:
                self.checkHoldTime(bar)
        # 持有空头仓位
        elif self.ownPosDict[symbol + "_SHORT"] > 0:
            firstOrder=self.transactionPrice[symbol+'0']
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop[symbol] = min(self.shortStop[symbol], self.intraTradeLowDict[symbol]+self.atrMultipler*atr)
            takeProfit = firstOrder-self.profitMultiper*self.atrMultipler*self.atrTrade[symbol]
            self.writeCtaLog('shortStop:%s' % (self.shortStop[symbol]))
            self.writeCtaLog('shortTakeProfit:%s'%(takeProfit))
            if bar.high >= self.shortStop[symbol]:
                self.coverCheckExtend(bar)
            elif bar.low < takeProfit:
                self.coverCheckExtend(bar)
            else:
                self.checkHoldTime(bar)

        self.putEvent()  # 每分钟更新一次UI界面

    def onBarPosition(self, bar):
        symbol = bar.vtSymbol
        # antiMartingle
        if (self.ownPosDict[symbol + "_LONG"] == 0) and (self.ownPosDict[symbol + "_SHORT"] == 0):
            self.transactionPrice[symbol+'0'] = 0
            self.nPos[symbol] = 0
        # holdLong
        elif (self.ownPosDict[symbol+'_LONG']>0) and (self.nPos[symbol] < 1):
            firstOrder = self.transactionPrice[symbol+'0']
            if (firstOrder/bar.close-1)>= self.addPct:
                self.buyCheckExtend(bar, self.lot*(self.addMultiper**(self.nPos[symbol]+1)))  # 加仓 2手、4手、8手
                self.nPos[symbol] += 1  # 多加仓1次
        # holdShort
        elif (self.ownPosDict[symbol + "_SHORT"] > 0) and (self.nPos[symbol] < 1):    # 持有空头仓位并且加仓次数不超过3次
            firstOrder = self.transactionPrice[symbol+'0']
            if (bar.close/firstOrder-1)>= self.addPct:
                self.shortCheckExtend(bar, self.lot*(self.addMultiper**(self.nPos[symbol]+1)))  # 加仓 2手、4手、8手
                self.nPos[symbol] += 1 # 多加仓1次
        self.writeCtaLog('self.nPos[symbol]:%s'%(self.nPos[symbol]))

    def on15MinBar(self, bar):
        symbol = bar.vtSymbol
        am15 = self.getArrayManager(symbol, "15m")

        if (not am15.inited):
            return

        # indicator
        rsi = ta.RSI(am15.close, self.rsiPeriod)
        rsiMa = ta.MA(rsi, self.rsiMaPeriod)
        rsiUpper, rsiMiddle, rsiLower = ta.BBANDS(rsi, self.rsiBBandPeriod)

        # phenomenon
        rsiBreakUpperBand = (rsiMa[-1]>rsiUpper[-2]) and (rsiMa[-2]<=rsiUpper[-2])
        rsiBreakLowerBand = (rsiMa[-1]<rsiLower[-2]) and (rsi[-2]>=rsiLower[-2])

        self.writeCtaLog('rsiMa:%s, rsiUpper:%s, rsiLower:%s'%rsiMa[-2:], rsiUpper[-2:], rsiLower[-2:])

        # unusualCondition
        if (self.ownPosDict[symbol + "_LONG"]>0) or (self.ownPosDict[symbol + "_SHORT"]>0):
            self.rsiBreakBand[symbol] = 0
            self.unusualStartTime[symbol]=None
        elif (self.ownPosDict[symbol + "_LONG"]==0) and (self.ownPosDict[symbol + "_SHORT"]==0):
            if rsiBreakUpperBand:
                self.rsiBreakBand[symbol] = 1
                self.unusualStartTime[symbol] = bar.datetime
            elif rsiBreakLowerBand:
                self.rsiBreakBand[symbol] = -1
                self.unusualStartTime[symbol] = bar.datetime

        if self.unusualStartTime[symbol]:
            if (bar.datetime - self.unusualStartTime[symbol])> timedelta(hours=self.unusualHour):
                self.rsiBreakBand[symbol] = 0
                self.unusualStartTime[symbol]=None

        self.writeCtaLog('regTrend: %s, rsiBreakBand:%s'%(self.regTrend[symbol], self.rsiBreakBand[symbol]))

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


        self.writeCtaLog('residualSma: %s, residualLma: %s'%(residualSma[-1], residualLma[-1]))
        # signal
        if residualUp:
            self.regTrend[symbol] = 1
        elif residualDn:
            self.regTrend[symbol] = -1
        else:
            self.regTrend[symbol] = 0

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

        if order.status in STATUS_FINISHED:
            if order.offset == OFFSET_OPEN:
                self.orderDict[symbol+'_OPEN'].remove(str(order.vtOrderID))
            elif order.offset == OFFSET_CLOSE:
                self.orderDict[symbol+'_CLOSE'].remove(str(order.vtOrderID))

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        symbol = trade.vtSymbol
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onTrade
        if trade.offset == OFFSET_OPEN:  # 判断成交订单类型
            self.transactionPrice[symbol+'%s'%self.nPos[symbol]] = trade.price # 记录成交价格
            self.openTime[symbol] = trade.tradeDatetime
        if trade.offset == OFFSET_CLOSE:
            self.openTime[symbol] = None

        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol+'_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol+'_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol+'_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol+'_SHORT'] -= int(trade.volume)
        self.writeCtaLog('tradeDatetime:%s, ownPosDict:%s'%(trade.tradeDatetime, self.ownPosDict))
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass