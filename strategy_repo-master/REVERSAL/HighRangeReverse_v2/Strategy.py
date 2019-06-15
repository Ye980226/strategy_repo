from vnpy.trader.utils.templates.orderTemplate import *
import numpy as np
import talib as ta


########################################################################
class StrategyHighRangeRevV2(OrderTemplate):
    className = 'StrategyHighRangeRevV2'
    author = 'Rich'

    # 参数列表，保存了参数的名称
    paramList = [
        'className',
        'author',
        'symbolList',  # 套利的品种对
        'maxBarSize',  # 预加载的bar数
        "ATRPeriod",
        "ATRLimit",
        "orderWaitingTime",  # 开仓等待时间
        "lot",
        "leftRiseBarNum",
        "leftRiseRange",
        "RiseReverseBars",
        "RisePointGap",
        "RiseProp",
        "leftFallBarNum",
        "leftFallRange",
        "FallReverseBars",
        "FallPointGap",
        "FallProp",
        "profitLimit",
        "moveRange",
    ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.symbol = self.symbolList[0]  # 待交易的品种
        self.orderDict = {"buy": set(), "short": set()}
        self.recentStart = {"buy": None, "short": None,
                            "updateBuy": True, "updateShort": True,
                            "inited": False
                            }
        self.lastaTime = {"buy": None, "short": None}

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(self.maxBarSize)  # 定义预加载bar数
        self.registerOnBar(self.symbol, "15m", None)

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.putEvent()

    # -----------------------------------------------------------------------
    def getPos(self, key):
        pos = 0
        for orderID in list(self.orderDict[key]):
            op = self._orderPacks[orderID]
            openVolume = op.order.tradedVolume
            closedVolume = self.orderClosedVolume(op)
            pos += (openVolume - closedVolume)
        return pos

    def outputPosAndOrd(self):
        self.writeCtaLog('打印当前的订单和仓位')
        self.writeCtaLog('订单:%s' % (self.orderDict,))
        self.writeCtaLog('仓位-buy:%s;short:%s' % (self.getPos("buy"), self.getPos("short")))

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    def entryOrder(self, sig, bar, stoploss):
        if sig > 0:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, self.symbol, bar.close * 1.01, self.lot,
                                      self.orderWaitingTime)
            for orderID in tlo.vtOrderIDs:
                # 将订单ID加到集合
                self.orderDict["buy"].add(orderID)
                op = self._orderPacks[orderID]
                self.setAutoExit(op, stoploss, None)  # 设置止盈止损
        elif sig < 0:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, self.symbol, bar.close * 0.99, self.lot,
                                      self.orderWaitingTime)
            for orderID in tlo.vtOrderIDs:
                self.orderDict["short"].add(orderID)
                op = self._orderPacks[orderID]
                self.setAutoExit(op, stoploss, None)

    def initBuyShort(self, am):
        for i in range(len(am.close)-self.leftRiseBarNum+1):
            if am.high[i+self.leftRiseBarNum-1] / am.low[i:i+self.leftRiseBarNum-1].min() - 1 > self.leftRiseRange:
                if self.recentStart["updateShort"]:
                    self.recentStart["short"] = am.datetime[i+self.leftRiseBarNum-1]
                    self.recentStart["updateShort"] = False
            else:
                self.recentStart["updateShort"] = True
            if am.low[i+self.leftRiseBarNum-1] / am.high[i:i+self.leftRiseBarNum-1].max() - 1 < -self.leftFallRange:  # 找到一个可以更新的左侧起点
                if self.recentStart["updateBuy"]:
                    self.recentStart["buy"] = am.datetime[i+self.leftRiseBarNum-1]
                    self.recentStart["updateBuy"] = False
            else:
                self.recentStart["updateBuy"] = True
        self.recentStart["inited"] = True

    def updateBuyAndShort(self, am):
        if am.high[-1] / am.low[-self.leftRiseBarNum:-1].min() - 1 > self.leftRiseRange:  # 找到一个可以更新的左侧起点
            if self.recentStart["updateShort"]:
                self.recentStart["short"] = am.datetime[-1]
                self.recentStart["updateShort"] = False
        else:
            self.recentStart["updateShort"] = True
        if am.low[-1] / am.high[-self.leftFallBarNum:-1].max() - 1 < -self.leftFallRange:  # 找到一个可以更新的左侧起点
            if self.recentStart["updateBuy"]:
                self.recentStart["buy"] = am.datetime[-1]
                self.recentStart["updateBuy"] = False
        else:
            self.recentStart["updateBuy"] = True

    def findShortSig(self, am):
        if self.recentStart["short"] is not None and self.recentStart["short"] in am.datetime:
            start = np.argwhere(am.datetime == self.recentStart["short"])[0][0]
            a = am.high[start:].argmax() + start
            ar1 = am.high[start:max(a - self.RiseReverseBars, 0)]
            ar2 = am.high[a + self.RiseReverseBars:]
            if len(ar1) == 0 and len(ar2) == 0:
                return 0, None, None, None
            if len(ar1) == 0 or len(ar2) == 0:
                if len(ar2) == 0:
                    b = a
                    a = ar1.argmax() + start
                if len(ar1) == 0:
                    b = ar2.argmax() + a + self.RiseReverseBars
            else:
                if ar1.max() > ar2.max():
                    b = a
                    a = ar1.argmax() + start
                else:
                    b = ar2.argmax() + a + self.RiseReverseBars
            if a > 0 and b != a + self.RiseReverseBars:
                if abs(am.high[a] / am.high[b] - 1) < self.RisePointGap:  # 两个高点接近
                    pivotLow = am.low[a + 1:b].min()
                    innerRange = am.high[a + 1:b].max() / pivotLow - 1
                    leftRiseRange = (am.high[a] / am.low[max(a - self.leftRiseBarNum, 0):a].min() - 1)
                    if leftRiseRange != 0:
                        prop = innerRange / abs(leftRiseRange)
                        if prop < self.RiseProp:
                            return -1, pivotLow, max(am.high[a], am.high[b]), am.datetime[a]
        return 0, None, None, None

    def findBuySig(self, am):
        if self.recentStart["buy"] is not None and self.recentStart["buy"] in am.datetime:
            start = np.argwhere(am.datetime == self.recentStart["buy"])[0][0]
            a = am.low[start:].argmin() + start
            ar1 = am.low[start:max(a - self.FallReverseBars, 0)]
            ar2 = am.low[a + self.FallReverseBars:]
            if len(ar1) == 0 and len(ar2) == 0:
                return 0, None, None, None
            if len(ar1) == 0 or len(ar2) == 0:
                if len(ar2) == 0:
                    b = a
                    a = ar1.argmin() + start
                if len(ar1) == 0:
                    b = ar2.argmin() + a + self.FallReverseBars
            else:
                if ar1.min() < ar2.min():
                    b = a
                    a = ar1.argmin() + start
                else:
                    b = ar2.argmin() + a + self.FallReverseBars
            if a > 0 and b != a + self.FallReverseBars:
                if abs(am.low[a] / am.low[b] - 1) < self.FallPointGap:  # 两个低点接近
                    pivotHigh = am.high[a + 1:b].max()
                    innerRange = pivotHigh / am.low[a + 1:b].min() - 1
                    leftFallRange = (am.low[a] / am.high[max(a - self.leftFallBarNum, 0):a].max() - 1)
                    if leftFallRange != 0:
                        prop = innerRange / abs(leftFallRange)
                        if prop < self.FallProp:
                            return 1, pivotHigh, min(am.low[a], am.low[b]), am.datetime[a]
        return 0, None, None, None

    def strategy(self, bar):
        # 计算信号
        am15 = self.getArrayManager(self.symbol, "15m")
        if am15.inited:
            ATRSeries = ta.ATR(am15.high, am15.low, am15.close, self.ATRPeriod) / am15.close[-1]
            ATR = ATRSeries[-1]
            if ATR <= self.ATRLimit:  # ATR低于某个阈值
                am = self.getArrayManager(bar.vtSymbol, freq="1m")
                if am.inited:
                    # 更新左侧高/低点位置
                    if not self.recentStart["inited"]:
                        self.initBuyShort(am)
                    else:
                        self.updateBuyAndShort(am)
                    shortSig, shortPivot, shortSt, shortArdt = self.findShortSig(am)
                    buySig, buyPivot, buySt, buyArdt = self.findBuySig(am)
                    if shortSig == -1:
                        if am.close[-1] < shortPivot <= am.close[-2]:
                            if shortArdt != self.lastaTime["short"] or len(self.orderDict["short"]) == 0:
                                self.lastaTime["short"] = shortArdt
                                self.entryOrder(-1, bar, shortSt)
                    if buySig == 1:
                        if am.close[-1] > buyPivot >= am.close[-2]:
                            if buyArdt != self.lastaTime["buy"] or len(self.orderDict["buy"]) == 0:
                                self.lastaTime["buy"] = buyArdt
                                self.entryOrder(1, bar, buySt)

    # 定时清除已经出场的单
    def delOrderID(self, opIDsets):
        for vtOrderID in list(opIDsets):
            op = self._orderPacks[vtOrderID]
            # 检查是否完全平仓
            if self.orderClosed(op):
                # 在记录中删除
                opIDsets.discard(vtOrderID)

    # 定时运行该方法，将已经结束的单从存放的集合中清除
    def cleanOrderDict(self):
        self.delOrderID(self.orderDict["buy"])
        self.delOrderID(self.orderDict["short"])

    def updateStopLoss(self, price):
        for orderID in list(self.orderDict["short"]):
            op = self._orderPacks[orderID]
            if op.order.tradedVolume != 0:  # 有进场
                if price / op.order.price_avg - 1 <= -self.profitLimit:  # 当前已实现不少于1%的盈利
                    if price / (1 - self.moveRange) < op.info["_AutoExitInfo"].stoploss:  # 1%移动止损
                        self.setAutoExit(op, price / (1 - self.moveRange), None)
        for orderID in list(self.orderDict["buy"]):
            op = self._orderPacks[orderID]
            if op.order.tradedVolume != 0:  # 有进场
                if price / op.order.price_avg - 1 >= self.profitLimit:  # 当前已实现不少于1%的盈利
                    if price / (1 + self.moveRange) > op.info["_AutoExitInfo"].stoploss:  # 1%移动止损
                        self.setAutoExit(op, price / (1 + self.moveRange), None)

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            self.lot = round(100 / bar.close, 4)
            # 移动止损
            self.updateStopLoss(bar.close)

        # 下单进场
        self.strategy(bar)
        self.checkOnPeriodEnd(bar)
        # 定时从集合中清除已出场的单
        self.cleanOrderDict()
        # 日志打印当前的订单和仓位
        self.outputPosAndOrd()

    # 实盘在5sBar中洗价
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        # 移动止损
        self.updateStopLoss(bar.close)
        self.checkOnPeriodEnd(bar)
