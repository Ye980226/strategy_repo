from vnpy.trader.utils.templates.orderTemplate import *
import talib as ta


########################################################################
class StrategyRetTrend(OrderTemplate):
    className = 'StrategyRetTrend'
    author = 'Rich'

    # 参数列表，保存了参数的名称
    paramList = [
        "className",
        "author",
        "name",
        "symbolList",
        "maxBarSize",
        "maxRetMeanListSize", # 均线序列的长度
        "meanRetBars", # 求收益率均值的周期长度
        "madParam", # mad去极值的参数
        "EMAPeriod", # ema周期 用来求收益率均值序列的EMA
        "meanEMAPeriod", # 远期收益率均值序列的EMA
        "maDiff", # 近期远期收益率均值的差
        "lot",
        "maxPos", # 最大仓位
        "orderWaitingTime",
        "timeframeMap"
    ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.symbol = self.symbolList[0]  # 待交易的品种
        self.lastBarTimeDict = {}  # 用于记录K线的最新时间
        self.orderDict = {
            "buy": set(),
            "short": set(),
        }
        self.ret_mean = np.asarray([])

    # 准备不同周期的K线数据
    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)
            self.lastBarTimeDict[timeframe] = None

    # 判断是否产生了个新bar——有新bar则进行信号计算
    def barPrepared(self, period):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False, None
        if self.lastBarTimeDict[period] is None or am.datetime[-1] > self.lastBarTimeDict[period]:
            return True, am
        else:
            return False, None

    # 更新记录am中最新一根K线的时间
    def updateLastBarTime(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.lastBarTimeDict[timeframe] = self.getArrayManager(self.symbol, timeframe).datetime[-1]

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(self.maxBarSize)  # 定义预加载bar数
        self.prepare_data()  # 准备不同周期的K线数据

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.putEvent()

    # -----------------------------------------------------------------------
    def outputPos(self):
        self.writeCtaLog('仓位:')
        self.writeCtaLog("buy:%s, short:%s" % (self.getPos("buy"), self.getPos("short")))

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    # 实盘在5sBar中洗价
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)

    # 定时清除已经出场的单
    def delOrderID(self, opIDsets):
        for vtOrderID in list(opIDsets):
            op = self._orderPacks[vtOrderID]
            # 检查是否完全平仓
            if self.orderClosed(op):
                # 在记录中删除
                opIDsets.discard(vtOrderID)

    # 定时运行该方法，将已经结束的单从存放的集合中清除
    def cleanOrderID(self):
        self.delOrderID(self.orderDict["buy"])
        self.delOrderID(self.orderDict["short"])

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)

        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot = round(100 / bar.close, 4)
            self.maxPos = self.lot * 2.5

        # 定时从集合中清除已出场的单
        self.cleanOrderID()
        # 执行策略逻辑
        self.strategy(bar, sigPeriod=self.timeframeMap["sigPeriod"])
        # 定时控制--结束
        self.checkOnPeriodEnd(bar)
        # 日志打印仓位
        self.outputPos()

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    def calMadedRet(self, ret, madParam):
        median = np.median(ret)
        tmp = np.median(abs(ret - median))
        ret = ret.clip(median - madParam * tmp, median + madParam * tmp)
        return ret

    def initRetMean(self, am):
        close = am.close
        retSeries = close[1:] / close[:-1] - 1
        for i in range(len(retSeries) - self.meanRetBars + 1):
            ret = self.calMadedRet(retSeries[i:i+self.meanRetBars], self.madParam)
            self.ret_mean = np.append(self.ret_mean, ret.mean())

    def getSignal(self, period="5m"):
        barPrepared, am = self.barPrepared(period)
        sig = 0
        exit_sig = 0
        if barPrepared:
            if len(self.ret_mean) == 0:
                self.initRetMean(am)
            else:
                close = am.close
                ret = self.calMadedRet((close[1:] / close[:-1] - 1)[-self.meanRetBars:], self.madParam)
                self.ret_mean = np.append(self.ret_mean, ret.mean())[-self.maxRetMeanListSize:]

            if len(self.ret_mean) >= self.maxRetMeanListSize:
                MA = ta.EMA(self.ret_mean, self.EMAPeriod)
                if MA[-1] - np.nanmean(MA[-self.meanEMAPeriod:-1]) >= self.maDiff > MA[-2] - np.nanmean(
                        MA[-self.meanEMAPeriod - 1:-2]):
                    sig = 1
                if MA[-1] - np.nanmean(MA[-self.meanEMAPeriod:-1]) <= -self.maDiff < MA[-2] - np.nanmean(
                        MA[-self.meanEMAPeriod - 1:-2]):
                    sig = -1
                if MA[-1] - np.nanmean(MA[-self.meanEMAPeriod:-1]) > 0 >= MA[-2] - np.nanmean(
                        MA[-self.meanEMAPeriod - 1:-2]):
                    exit_sig = 1
                if MA[-1] - np.nanmean(MA[-self.meanEMAPeriod:-1]) < 0 <= MA[-2] - np.nanmean(
                        MA[-self.meanEMAPeriod - 1:-2]):
                    exit_sig = -1
        return sig, exit_sig

    def strategy(self,
                 bar,
                 sigPeriod="5m"
                 ):
        sig, exit_sig = self.getSignal(period=sigPeriod)
        self.exitOrder(exit_sig)
        self.entryOrder(sig, bar.close)
        # 更新记录am中最新一根K线的时间
        self.updateLastBarTime()

    # 下单出场
    def exitOrder(self, sig):
        if sig < 0:  # 全平多头
            for vtOrderID in list(self.orderDict["buy"]):
                op = self._orderPacks[vtOrderID]
                self.composoryClose(op)
        if sig > 0:  # 全平空头
            for vtOrderID in list(self.orderDict["short"]):
                op = self._orderPacks[vtOrderID]
                self.composoryClose(op)

    # 计算对应level上开了多少仓
    def getPos(self, level="buy"):
        pos = 0
        for orderID in list(self.orderDict[level]):
            op = self._orderPacks[orderID]
            openVolume = op.order.tradedVolume
            closedVolume = self.orderClosedVolume(op)
            pos += (openVolume - closedVolume)
        return pos

    # 根据当前价格所处的位置挂网进场
    def entryOrder(self, sig, priceNow):
        if sig < 0 and self.getPos("short") + self.lot <= self.maxPos:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, self.symbol, priceNow * 0.99, self.lot,
                                      self.orderWaitingTime)
            for orderID in tlo.vtOrderIDs:
                # 将订单ID加到集合
                self.orderDict["short"].add(orderID)
        elif sig > 0 and self.getPos("buy") + self.lot <= self.maxPos:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, self.symbol, priceNow * 1.01, self.lot,
                                      self.orderWaitingTime)
            for orderID in tlo.vtOrderIDs:
                # 将订单ID加到集合
                self.orderDict["buy"].add(orderID)
