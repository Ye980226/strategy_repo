from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from adxDiSignalClass import adxDiSignal


########################################################################
class adxDiStrategy(OrderTemplate):
    className = 'adxDi'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 分批进场手数
                 'lot1', 'lot2',
                 # 品种列表
                 'symbolList',
                 # envParameter 计算ADX环境的参数
                 'adxPeriod', 'adxMaPeriod', 'adxMaType', 'adxThreshold',
                 # signalParameter 计算信号的参数
                 'diPeriod','signalMaPeriod', 'signalMaType',
                 # 追踪止损的百分比
                 'trailingPct', 
                 # 出场后停止的小时
                 'stopControlTime',
                 # 价格变化百分比加仓， 加仓的乘数
                 'addPct','addMultipler',
                 # 低波动率过滤阈值
                 'volPeriod', 'lowVolThreshold',
                 # 分批止盈价格 
                 'takeProfitFirstPct', 'takeProfitSecondPct',
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
        self.barPeriod = 500
        engineType = self.getEngineType()  # 判断engine模式
        self.symbol = self.symbolList[0]

        # varialbes
        self.orderDict = {'orderFirstSet':set(), 'orderSecondSet': set()}
        self.orderAllList = []
        self.lastOrderDict = {'nextExecuteTime': datetime(2000, 1, 1)}
        self.nPos = 0
        # 打印全局信号的字典
        self.globalStatus = {}
    
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
    
    def moveStopLoss(self, bar, orderSet):
        for orderId in list(orderSet):
            op = self._orderPacks[orderId]
            # 通过改一张单绑定的AutoExitInfo属性修改止损止盈
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                sl = op.info["sl"]
                if op.order.direction == constant.DIRECTION_LONG:
                    if (bar.high - ae.stoploss) >= 2 * sl:
                        self.setAutoExit(op, (ae.stoploss+sl)*1.001)
                        self.globalStatus['longTrailingStopLoss'] = (ae.stoploss+sl)*1.001
                elif op.order.direction == constant.DIRECTION_SHORT:
                    if (ae.stoploss - bar.low) >= 2 * sl:
                        self.setAutoExit(op, (ae.stoploss - sl)*0.999)
                        self.globalStatus['shortTrailingStopLoss'] = (ae.stoploss-sl)*0.999

    # 获得执行价格
    def priceExecute(self, bar):
        if bar.vtSymbol in self._tickInstance:
            tick = self._tickInstance[bar.vtSymbol]
            if tick.datetime >= bar.datetime:
                return tick.upperLimit * 0.99, tick.lowerLimit*1.01
        return bar.close*1.02, bar.close*0.98


    # 获取当前的持有仓位
    def getHoldVolume(self, orderSet):
        pos = 0
        for orderID in orderSet:
            op = self._orderPacks[orderID]
            holdVolume = op.order.tradedVolume
            closedVolume = self.orderClosedVolume(op)
            pos+= (holdVolume-closedVolume)
        return pos
    
    # 实盘在5sBar中洗价
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)
        for idSet in self.orderDict.values():
            self.delOrderID(idSet)
            self.moveStopLoss(bar, idSet)

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)
        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot1 = int(200000 / bar.close)
            self.lot2 = int(100000 / bar.close)
        # 定时清除已出场的单
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)

            for idSet in self.orderDict.values():
                self.delOrderID(idSet)
                self.moveStopLoss(bar, idSet)

        # 执行策略逻辑
        self.strategy(bar)

    def on5MinBar(self, bar):
        engineType = self.getEngineType()  # 判断engine模式
        if engineType != 'backtesting':
            self.writeCtaLog('globalStatus%s'%(self.globalStatus))
            self.writeCtaLog('firstVolume:%s, secondVolume:%s'%(self.getHoldVolume(self.orderDict['orderFirstSet']), self.getHoldVolume(self.orderDict['orderSecondSet'])))

    def strategy(self, bar):
        envPeriod= self.timeframeMap["envPeriod"]
        filterPeriod= self.timeframeMap["filterPeriod"]
        trendPeriod= self.timeframeMap["trendPeriod"]
        signalPeriod= self.timeframeMap["signalPeriod"]
        addPosPeriod = self.timeframeMap["addPosPeriod"]
                
        # 根据出场信号出场
        exitSig = self.exitSignal(envPeriod, filterPeriod)
        self.exitOrder(exitSig)

        # 根据进场信号进场
        entrySig = self.entrySignal(envPeriod, filterPeriod, trendPeriod, signalPeriod)
        self.entryOrder(entrySig, bar)

        # 根据信号加仓
        addPosSig = self.addPosSignal(addPosPeriod)
        self.addPosOrder(bar, addPosSig)

    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']

    def exitSignal(self, envPeriod, filterPeriod):
        exitSignal = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        if arrayPrepared1 and arrayPrepared2:
            algorithm = adxDiSignal()
            adxCanTrade, adxTrend, adxMa = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade = algorithm.fliterVol(amFilter, self.paraDict)
            exitSignal = 1 if filterCanTrade == -1 else -1
        return exitSignal

    def exitOrder(self, exitSignal):
        if exitSignal>0:
            for orderID in (self.orderDict['orderFirstSet']|self.orderDict['orderSecondSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)
        else:
            pass
    
    def entrySignal(self, envPeriod, filterPeriod, trendPeriod, signalPeriod):
        entrySignal = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3, amTrend = self.arrayPrepared(trendPeriod)
        arrayPrepared4, amSignal = self.arrayPrepared(signalPeriod)
        arrayPrepared = arrayPrepared1 and arrayPrepared2 and arrayPrepared3 and arrayPrepared4
        if arrayPrepared:
            algorithm = adxDiSignal()
            adxCanTrade, adxTrend, adxMa = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade = algorithm.fliterVol(amFilter, self.paraDict)
            trendDirection, plusDi, minusDi = algorithm.diSignal(amTrend, self.paraDict)
            signalMaDirection, signalMa = algorithm.maSignal(amSignal, self.paraDict)
            self.globalStatus['adxCanTrade'] = adxCanTrade
            self.globalStatus['filterCanTrade'] = filterCanTrade
            self.globalStatus['trendDirection'] = trendDirection
            self.globalStatus['signalMaDirection'] = signalMaDirection
            self.globalStatus['adxTrend'] = adxTrend[-1]
            self.globalStatus['adxMa'] = adxMa[-1]
            self.globalStatus['signalMa'] = signalMa[-3:]
            
            if (adxCanTrade == 1) and (filterCanTrade == 1):
                if (trendDirection == 1) and not self.isStopControled():
                    if (signalMaDirection == 1):
                        entrySignal = 1
                if (trendDirection == -1) and not self.isStopControled():
                    if (signalMaDirection == -1):
                        entrySignal = -1
        return entrySignal

    def entryOrder(self, entrySignal, bar):
        # 避免onTrade没走完就走加仓的方法设置的开关
        buyExecute, shortExecute = self.priceExecute(bar)
        engineType = self.getEngineType()
        if entrySignal ==1 and not self.isStopControled():
            if not (self.orderDict['orderFirstSet'] or self.orderDict['orderSecondSet']):
                for orderID2 in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot2, 120).vtOrderIDs:                
                    self.orderDict['orderSecondSet'].add(orderID2)
                longPos = self.lot1//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot1, longPos, self.totalSecond, self.stepSecond)
                orderID1 = stepOrder.parentID
                self.orderDict['orderFirstSet'].add(orderID1)
                self.orderAllList.append(orderID1)
        elif entrySignal ==-1 and not self.isStopControled():
            if not (self.orderDict['orderFirstSet'] or self.orderDict['orderSecondSet']):
                for orderID2 in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot2, 120).vtOrderIDs:
                    self.orderDict['orderSecondSet'].add(orderID2)
                shortPos = self.lot1//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot1, shortPos, self.totalSecond, self.stepSecond)
                orderID1 = stepOrder.parentID
                self.orderDict['orderFirstSet'].add(orderID1)
                self.orderAllList.append(orderID1)

    # 计算可加仓的信号
    def addPosSignal(self, addPosPeriod):
        erCanAddPos = 0
        arrayPrepared, amAddPos = self.arrayPrepared(addPosPeriod)
        if arrayPrepared:
            algorithm = adxDiSignal()
            erCanAddPos, erSma, erLma = algorithm.erAdd(amAddPos, self.paraDict)
        return erCanAddPos

    # 通过上一张单来设置止损止盈
    def addPosOrder(self, bar, addPosSignal):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not self.orderDict['orderFirstSet']:
            self.nPos = 0
            self.orderAllList = []
        else:
            lastOrderID = self.orderAllList[-1]
            op = self._orderPacks[lastOrderID]
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                sl = op.info["sl"]
                lastOrder = op.order.price_avg
                algorithm = adxDiSignal()
                if addPosSignal:
                    if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                        if ((bar.close/lastOrder - 1) >= self.addPct) and ((bar.close/lastOrder - 1)<=2*self.addPct):
                            self.nPos += 1
                            addPosLot = int(algorithm.addLotList(self.paraDict)[self.nPos-1]*self.lot1)
                            longAddPos = addPosLot//self.orderTime
                            self.globalStatus['longAddPos'] = (self.nPos, longAddPos)
                            stepAddOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, addPosLot, longAddPos, self.totalSecond, self.stepSecond)
                            addOrderID = stepAddOrder.parentID
                            self.orderAllList.append(addOrderID)
                            addOp = self._orderPacks[addOrderID]
                            addOp.info["sl"] = sl
                            self.setAutoExit(addOp, ae.stoploss, ae.takeprofit)
                            self.orderDict['orderFirstSet'].add(addOrderID) 
                 
                    elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                        if ((lastOrder/bar.close - 1) >= self.addPct) and ((lastOrder/bar.close - 1) <= 2*self.addPct):
                            self.nPos += 1
                            addPosLot = int(algorithm.addLotList(self.paraDict)[self.nPos-1]*self.lot1)
                            shortAddPos = addPosLot//self.orderTime
                            self.globalStatus['shortAddPos'] = (self.nPos, shortAddPos)
                            stepAddOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, addPosLot, shortAddPos, self.totalSecond, self.stepSecond)
                            addOrderID = stepAddOrder.parentID
                            self.orderAllList.append(addOrderID)
                            addOp = self._orderPacks[addOrderID]
                            addOp.info["sl"] = sl
                            self.setAutoExit(addOp, ae.stoploss, ae.takeprofit)
                            self.orderDict['orderFirstSet'].add(addOrderID) 

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        self.setStop(order)

    def setStop(self, order):
        op = self._orderPacks.get(order.vtOrderID, None)
        # 判断是否该策略下的开仓
        if op:
            # 如果没有加过仓就设置初始的止损止盈
            if order.offset == constant.OFFSET_OPEN:
                if self.nPos == 0 and order.price_avg!=0:
                    sl_gap = order.price_avg*self.trailingPct
                    tp1 = order.price_avg*self.takeProfitFirstPct
                    tp2 = order.price_avg*self.takeProfitSecondPct
                    if order.direction == constant.DIRECTION_LONG:
                        if op.vtOrderID in self.orderDict['orderFirstSet']:
                            self.setAutoExit(op, (order.price_avg-sl_gap), order.price_avg+tp1)
                            op.info["sl"] = sl_gap
                            self.globalStatus['orderFirstLong'] = {'SL': order.price_avg-sl_gap, 'TP': order.price_avg+tp1}
                        elif op.vtOrderID in self.orderDict['orderSecondSet']:
                            self.setAutoExit(op, (order.price_avg-sl_gap), order.price_avg+tp2)
                            op.info["sl"] = sl_gap
                            self.globalStatus['orderSecondLong'] = {'SL': order.price_avg-sl_gap, 'TP': order.price_avg+tp2}
                    elif order.direction == constant.DIRECTION_SHORT:
                        if op.vtOrderID in self.orderDict['orderFirstSet']:
                            self.setAutoExit(op, (order.price_avg+sl_gap), order.price_avg-tp1)
                            op.info["sl"] = sl_gap
                            self.globalStatus['orderFirstShort'] = {'SL': order.price_avg+sl_gap, 'TP': order.price_avg-tp1}
                        elif op.vtOrderID in self.orderDict['orderSecondSet']:
                            self.setAutoExit(op, (order.price_avg+sl_gap), order.price_avg-tp2)
                            op.info["sl"] = sl_gap
                            self.globalStatus['orderSecondShort'] = {'SL': order.price_avg+sl_gap, 'TP': order.price_avg-tp2}

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        super().onTrade(trade)
        pass

    def onStopOrder(self, so):
        """停止单推送"""
        pass