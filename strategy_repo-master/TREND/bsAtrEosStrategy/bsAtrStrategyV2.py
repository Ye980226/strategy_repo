from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from bsAtrSignalClass import bsAtrSignal
########################################################################
class bsAtrStrategy(OrderTemplate):
    className = 'bsAtr'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 进场手数
                 'lot',
                 # 品种列表
                 'symbolList',
                 # envParameter 计算ADX环境的参数
                 'adxPeriod','adxMaPeriod',
                 'adxLowThreshold','adxMaxThreshold'
                 # signalParameter 计算信号的参数
                 'smaPeriod','lmaPeriod',
                 'atrPeriod','atrSmallMultiplier','atrBigMultiplier',
                 # 出场后停止的小时
                 'stopControlTime',
                 # 波动率过滤阈值
                 'volPeriod','highVolthreshold', 'lowVolthreshold',
                 # 加仓信号指标
                 'corPeriod','maCorPeriod','lotMultiplier',
                 # 价格变化百分比加仓， 加仓的乘数
                 'addPct','addMultiplier',
                 # 可加仓的次数
                 'posTime',
                 # 时间周期
                 'timeframeMap',
                 #  总秒，间隔，下单次数
                 'totalSecond', 'stepSecond','orderTime'
                ]

    # 变量列表，保存了变量的名称
    varList = [
                'nPos'
               ]
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.paraDict = setting
        self.barPeriod = 600
        self.symbol = self.symbolList[0]

        # varialbes
        self.orderDict = {'orderLongSet':set(), 'orderShortSet':set()}
        self.orderLastList = []
        self.lastOrderDict = {'nextExecuteTime': datetime(2000, 1, 1)}
        self.nPos = 0

        # 打印全局信号的字典
        self.globalStatus = {}
        self.chartLog = {
                        'datetime':[],
                        'upperBand':[],
                        'lowerBand':[],
                        'lma':[],
                        'sma':[]
                        }

    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)

    def arrayPrepared(self, period):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            return False, None
        else:
            return True, am

    # ----------------------------------------------------------------------
    def onInit(self):
        self.setArrayManagerSize(self.barPeriod)
        self.prepare_data()
        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        self.putEvent()

    # 定时清除已经出场的单
    def delOrderID(self, orderSet):
        for orderId in list(orderSet):
            op = self._orderPacks[orderId]
            # 检查是否完全平仓
            if self.orderClosed(op):
                # 在记录中删除
                orderSet.discard(orderId)
                self.lastOrderDict['nextExecuteTime'] = self.currentTime + timedelta(hours=self.stopControlTime)
    
    # 获得执行价格
    def priceExecute(self, bar):
        if bar.vtSymbol in self._tickInstance:
            tick = self._tickInstance[bar.vtSymbol]
            if tick.datetime >= bar.datetime:
                return tick.upperLimit * 0.99, tick.lowerLimit*1.01
        return bar.close*1.02, bar.close*0.98

    def getHoldVolume(self, orderSet):
        pos = 0
        for orderID in orderSet:
            op = self._orderPacks[orderID]
            holdVolume = op.order.tradedVolume
            pos+= holdVolume
        return pos

    # 实盘在5sBar中洗价,并且在5sBar下执行出场
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)
        for idSet in self.orderDict.values():
            self.delOrderID(idSet)
        # 执行策略逻辑
        self.strategy(bar)

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)
        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot = int(200000 / bar.close)
            # 定时清除已出场的单
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)
            for idSet in self.orderDict.values():
                self.delOrderID(idSet)
            # 执行策略逻辑
            self.strategy(bar)


    def on5MinBar(self, bar):
        engineType = self.getEngineType()  # 判断engine模式
        if engineType != 'backtesting':
            self.writeCtaLog('globalStatus%s'%(self.globalStatus))
            self.writeCtaLog('longVolume:%s, shortVolume:%s'%(self.getHoldVolume(self.orderDict['orderLongSet']), self.getHoldVolume(self.orderDict['orderShortSet'])))
            self.notifyPosition('longVolume', self.getHoldVolume(self.orderDict['orderLongSet']), 'ChannelPos')
            self.notifyPosition('shortVolume', self.getHoldVolume(self.orderDict['orderShortSet']), 'ChannelPos')

    def strategy(self, bar):
        envPeriod= self.timeframeMap["envPeriod"]
        filterPeriod= self.timeframeMap["filterPeriod"]
        signalPeriod= self.timeframeMap["signalPeriod"]
        tradePeriod= self.timeframeMap["tradePeriod"]
        addPosPeriod = self.timeframeMap["addPosPeriod"]
                
        # 根据出场信号出场
        upperBandSma, lowerBandSma, upperBandlma, lowerBandlma = self.exitSignal(envPeriod, signalPeriod)
        
        if len(upperBandlma) and len(lowerBandlma):
            self.exitOrder(bar, upperBandSma, lowerBandSma, upperBandlma, lowerBandlma)

        # 根据进场信号进场
        entrySig = self.entrySignal(envPeriod, filterPeriod, signalPeriod, tradePeriod)
        self.entryOrder(bar, entrySig)

        # 根据信号加仓
        addPosSig = self.addPosSignal(addPosPeriod)
        self.addPosOrder(bar, addPosSig)

    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']

    def exitSignal(self, envPeriod, signalPeriod):
        upperBandSma, lowerBandSma, upperBandlma, lowerBandlma = np.array([]), np.array([]), np.array([]), np.array([])
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amSignal = self.arrayPrepared(signalPeriod)
        
        algorithm = bsAtrSignal()
        if arrayPrepared1 and arrayPrepared2:
            upperBandSma, lowerBandSma, sma = algorithm.atrExitSmaBand(amSignal, self.paraDict)
            upperBandlma, lowerBandlma, lma = algorithm.atrExitSmaBand(amSignal, self.paraDict)

        return upperBandSma, lowerBandSma, upperBandlma, lowerBandlma
    
    def exitOrder(self, bar, upperBandSma, lowerBandSma, upperBandlma, lowerBandlma):
        exitLongTouchLower = (bar.low < lowerBandSma[-1]) or (bar.low < lowerBandlma[-1])
        exitShortTouchUpper = (bar.high > upperBandSma[-1]) or (bar.high > upperBandlma[-1])
        if exitLongTouchLower:
            for orderID in (self.orderDict['orderLongSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)
        elif exitShortTouchUpper:
            for orderID in (self.orderDict['orderShortSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

        # exitLongTouchSma = (bar.low < sma[-1])
        # exitShortTouchSma = (bar.high > sma[-1])
        # exitLongTonchLma = (bar.low < lma[-1])
        # exitShortTonchLma = (bar.high > lma[-1])

        # if adxCanTrade==1:
        #     if exitLongTonchLma:
        #         for orderID in (self.orderDict['orderLongSet']):
        #             op = self._orderPacks[orderID]
        #             self.composoryClose(op)
        #     elif exitShortTonchLma:
        #         for orderID in (self.orderDict['orderShortSet']):
        #             op = self._orderPacks[orderID]
        #             self.composoryClose(op)
        # elif adxCanTrade==-1:
        #     if exitLongTouchSma:
        #         for orderID in (self.orderDict['orderLongSet']):
        #             op = self._orderPacks[orderID]
        #             self.composoryClose(op)
        #     elif exitShortTouchSma:
        #         for orderID in (self.orderDict['orderShortSet']):
        #             op = self._orderPacks[orderID]
        #             self.composoryClose(op)

    def entrySignal(self, envPeriod, filterPeriod, signalPeriod, tradePeriod):
        entrySignal = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3, amSignal = self.arrayPrepared(signalPeriod)
        arrayPrepared4, amTrade = self.arrayPrepared(tradePeriod)
        arrayPrepared = arrayPrepared1 and arrayPrepared2 and arrayPrepared3 and arrayPrepared4
        algorithm = bsAtrSignal()
        if arrayPrepared:
            adxCanTrade, adxTrend = algorithm.adxEnvV2(amEnv, self.paraDict)
            filterCanTrade = algorithm.fliterVol(amFilter, self.paraDict)
            if adxCanTrade==1:
                upperBand, lowerBand, sma, lma = algorithm.atrNorrowBand(amSignal, self.paraDict)
            elif adxCanTrade == -1:
                upperBand, lowerBand, sma, lma = algorithm.atrWideBand(amSignal, self.paraDict)
            breakHighest = (amTrade.close[-1]>upperBand[-2])
            breakLowest = (amTrade.close[-1]<lowerBand[-2])

            self.globalStatus['adxCanTrade'] = adxCanTrade
            self.globalStatus['filterCanTrade'] = filterCanTrade
            self.globalStatus['breakHighest'] = breakHighest
            self.globalStatus['breakLowest'] = breakLowest
            self.globalStatus['adxTrend'] = adxTrend[-1]
            self.globalStatus['upperBand'] = upperBand[-1]
            self.globalStatus['lowerBand'] = lowerBand[-1]

            self.chartLog['datetime'].append(datetime.strptime(amSignal.datetime[-1], "%Y%m%d %H:%M:%S"))
            self.chartLog['upperBand'].append(upperBand[-1])
            self.chartLog['lowerBand'].append(lowerBand[-1])
            self.chartLog['sma'].append(sma[-1])
            self.chartLog['lma'].append(lma[-1])

            if filterCanTrade == 1:
                if not self.isStopControled():
                    if breakHighest:
                        entrySignal = 1
                    elif breakLowest:
                        entrySignal = -1
        return entrySignal

    def entryOrder(self, bar, entrySignal):
        engineType = self.getEngineType()  # 判断engine模式
        buyExecute, shortExecute = self.priceExecute(bar)
        lotSize = self.lot * self.lotMultiplier
        if entrySignal ==1:
            if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
                # 如果回测直接下单，如果实盘就分批下单
                longPos = self.lot//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot, longPos, self.totalSecond, self.stepSecond)                 
                orderID = stepOrder.parentID
                self.orderDict['orderLongSet'].add(orderID)
                self.orderLastList.append(orderID)

        elif entrySignal ==-1:
            if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
                shortPos = self.lot//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot, shortPos, self.totalSecond, self.stepSecond)
                orderID = stepOrder.parentID                
                self.orderDict['orderShortSet'].add(orderID)
                self.orderLastList.append(orderID)

    # 计算可加仓的信号
    def addPosSignal(self, addPosPeriod):
        corCanAddPos = 1
        # arrayPrepared, amAddPos = self.arrayPrepared(addPosPeriod)
        # algorithm = bsAtrSignal()
        # if arrayPrepared:  
        #     corCanAddPos = algorithm.corAdd(amAddPos, self.paraDict)
        return corCanAddPos
   # 通过上一张单来设置止损止盈
    def addPosOrder(self, bar, addPosSignal):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
            self.nPos = 0
            self.orderLastList = []
        else:
            lastOrderID = self.orderLastList[-1]
            op = self._orderPacks[lastOrderID]
            lastOrder = op.order.price_avg
            if lastOrder!=0:
                if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                    if addPosSignal==1:
                        if ((bar.close/lastOrder - 1) >= self.addPct) and ((bar.close/lastOrder - 1)<=2*self.addPct):
                        # if (lastOrder/bar.close - 1) >= self.addPct:
                            self.nPos += 1
                            addPosLot = int(self.lotMultiplier* self.lot * (self.addMultiplier**self.nPos))
                            for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, addPosLot, 60).vtOrderIDs:
                                self.globalStatus['addPos'] = (self.nPos, addPosLot)
                                self.orderLastList.append(orderID)
                                addOp = self._orderPacks[orderID]
                                self.orderDict['orderLongSet'].add(orderID)                    
                elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                    if addPosSignal==-1:
                        if ((lastOrder/bar.close - 1) >= self.addPct) and ((lastOrder/bar.close - 1) <= 2*self.addPct):
                        # if (bar.close/lastOrder - 1) >= self.addPct:
                            self.nPos += 1
                            addPosLot = int(self.lotMultiplier*self.lot*(self.addMultiplier**self.nPos))
                            for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, addPosLot, 60).vtOrderIDs:
                                self.globalStatus['addPos'] = (self.nPos, addPosLot)
                                self.orderLastList.append(orderID)
                                addOp = self._orderPacks[orderID]
                                self.orderDict['orderShortSet'].add(orderID)                                    
    
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        op = self._orderPacks[order.vtOrderID]
        if not self.isFake(op):
            if order.status == STATUS_UNKNOWN:
                self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                        % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
            if order.status == STATUS_REJECTED:
                self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                        % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
            if order.thisTradedVolume != 0:
                content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s, tradedVolume:%s'%\
                        (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price_avg, order.tradedVolume)
                # self.mail(content)

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        pass

    def onStopOrder(self, so):
        pass