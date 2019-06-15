from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from MAGlueSignalClass import MAGlueSignal
########################################################################
class MAGlueStrategy(OrderTemplate):
    className = 'MAGlueStrategy'
    author = 'sky'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 进场手数
                 'lot',
                 # 品种列表
                 'symbolList',
                 # maParameter 计算信号的参数
                 'Window1','Window2','Window3','Window4',
                 # 出场后停止的小时
                 'stopControlTime',
                 # 加仓信号指标
                 'corPeriod','maCorPeriod','lotMultiplier',
                 # 可加仓的次数
                 'posTime',
                 # 止损止盈参数
                 "takeProfitPct", "stopLossPct",
                 # 持有时间管理
                'holdTime','expectReturn',
                 # 时间周期
                 'timeframeMap',
                 #  总秒，间隔，下单次数
                 'totalSecond', 'stepSecond','orderTime'
                ]

    # 变量列表，保存了变量的名称
    varList = [
                'nPos',
                'intraTradeHighDict',
                'intraTradeLowDict',
                'longStop',
                'shortStop'
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
        self.longStop = 0
        self.shortStop = 999999
        self.intraTradeHighDict = 0
        self.intraTradeLowDict = 999999
        # 打印全局信号的字典

        self.globalStatus = {}
        self.chartLog = {
                        'datetime':[],
                        'agg_value':[],
                        'throld':[],
                        'SMa':[],
                        'LMa':[]
                        }

    # 注册所有timeframeMap的时间周期数据
    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)
    
    # 检查数组是否已经有足够的长度
    def arrayPrepared(self, period):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            return False, None
        else:
            return True, am

    # ----------------------------------------------------------------------
    # 启动初始化加载数据
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
    
    # 移动平保止损
    def moveStopLoss(self, bar, orderSet):
        for orderId in list(orderSet):
            op = self._orderPacks[orderId]
            print('op:%s'%(op))
            # 通过改一张单绑定的AutoExitInfo属性修改止损止盈
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                sl = op.info['slGap']
                if op.order.direction == constant.DIRECTION_LONG:
                    if (bar.high - ae.stoploss) >= 2 * sl:
                        self.setAutoExit(op, op.order.price_avg*1.001)
                elif op.order.direction == constant.DIRECTION_SHORT:
                    if (ae.stoploss - bar.low) >= 2 * sl:
                        self.setAutoExit(op, op.order.price_avg*0.999)

    # 获得执行价格
    def priceExecute(self, bar):
        if bar.vtSymbol in self._tickInstance:
            tick = self._tickInstance[bar.vtSymbol]
            if tick.datetime >= bar.datetime:
                return tick.upperLimit * 0.99, tick.lowerLimit*1.01
        return bar.close*1.02, bar.close*0.98

    # 获取当前持仓量
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
            # #吊灯止损
            if not self.orderDict['orderLongSet'] or not self.orderDict['orderShortSet']:
                self.longStop = 0
                self.shortStop = 999999
                self.intraTradeHighDict = 0
                self.intraTradeLowDict = 999999
            elif self.orderDict['orderLongSet']:
                self.intraTradeHighDict = max(self.intraTradeHighDict,bar.high)
                self.longStop = self.intraTradeHighDict * (1 - 0.015)
            elif self.orderDict['orderShortSet']:
                self.intraTradeLowDict = min(self.intraTradeLowDict,bar.low)
                self.shortstop = self.intraTradeLowDict * (1 + 0.015)
            # 回测时的下单手数按此方法调整
            self.lot = int(200000 / bar.close)
            # 定时清除已出场的单
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)

            # 输入订单ID执行删除已完成订单与移动止损
            for idSet in self.orderDict.values():
                self.delOrderID(idSet)
                #self.moveStopLoss(bar, idSet)

            
            # #过滤出场
            
            # 执行策略逻辑
            self.strategy(bar)


    def on5MinBar(self, bar):
        engineType = self.getEngineType()  # 判断engine模式
        if engineType != 'backtesting':
            self.writeCtaLog('globalStatus%s'%(self.globalStatus))
            self.writeCtaLog('longVolume:%s, shortVolume:%s'%(self.getHoldVolume(self.orderDict['orderLongSet']), self.getHoldVolume(self.orderDict['orderShortSet'])))

    def strategy(self, bar):
        envPeriod= self.timeframeMap["envPeriod"]
        filterPeriod= self.timeframeMap["filterPeriod"]
        tradePeriod= self.timeframeMap["tradePeriod"]
                
        # # 根据出场信号出场
        # self.exitOrder(bar,self.longStop,self.shortStop)
        # 根据进场信号进场
        entrySig = self.entrySignal(filterPeriod, tradePeriod,envPeriod)
        self.entryOrder(bar, entrySig)

        # # 根据信号加仓


    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']
    
    def exitOrder(self, bar, longStop,shortStop):

        exitLong = (bar.low< self.longStop)
        exitShort = (bar.high> self.shortStop)

        if exitLong:
            for orderID in (self.orderDict['orderLongSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

        elif exitShort:
            for orderID in (self.orderDict['orderShortSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

    def entrySignal(self,envPeriod,filterPeriod,tradePeriod):
        entrySignal = 0
        arrayPrepared1,amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2,amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3,amTrade = self.arrayPrepared(tradePeriod)
        arrayPrepared = arrayPrepared2 and arrayPrepared3 and arrayPrepared1
        algorithm = MAGlueSignal()

        if arrayPrepared:
            
            GlueSignal,agg_value,throld = algorithm.Glue_Signal(amEnv, self.paraDict)
            adxCanTrade, adxTrend, adxMa = algorithm.maSignal(amEnv, self.paraDict)
            signalMaDirection,SMa,LMa = algorithm.maSignal(amFilter, self.paraDict)
            self.chartLog['datetime'].append(datetime.strptime(amFilter.datetime[-1], "%Y%m%d %H:%M:%S"))

            self.chartLog['agg_value'].append(agg_value[-1])
            self.chartLog['throld'].append(throld)

            self.chartLog['SMa'].append(SMa[-1])
            self.chartLog['LMa'].append(LMa[-1])

            if GlueSignal ==1  and adxCanTrade:
                if signalMaDirection == 1:
                    entrySignal = 1
            elif GlueSignal == -1  and adxCanTrade:
                if signalMaDirection == -1:
                    entrySignal = -1

        return entrySignal

    def entryOrder(self, bar, entrySignal):
        engineType = self.getEngineType()  # 判断engine模式
        buyExecute, shortExecute = self.priceExecute(bar)
        lotSize = self.lot * self.lotMultiplier
        if not self.isStopControled():
            if entrySignal ==1 and not self.orderDict['orderShortSet']:
                # if not self.orderDict:
                # if self.orderDict['orderShortSet'] :
                #     for orderID in (self.orderDict['orderShortSet']):
                #         op = self._orderPacks[orderID]
                #         self.composoryClose(op)
                if not self.orderDict['orderLongSet']:
                    # 如果回测直接下单，如果实盘就分批下单
                    longPos = self.lot//self.orderTime
                    stepOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot, longPos, self.totalSecond, self.stepSecond)                 
                    orderID = stepOrder.parentID
                    self.orderDict['orderLongSet'].add(orderID)
                    self.orderLastList.append(orderID)
                    # 获取op对象，设置最长持有时间
                    op = self._orderPacks[orderID]
                    self.setConditionalClose(op, self.holdTime, self.expectReturn)

            elif entrySignal ==-1 and not self.orderDict['orderLongSet']:
                # if self.orderDict['orderLongSet']:
                #     for orderID in (self.orderDict['orderLongSet']):
                #         op = self._orderPacks[orderID]
                #         self.composoryClose(op)
                if not self.orderDict['orderShortSet']:
                    shortPos = self.lot//self.orderTime
                    stepOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot, shortPos, self.totalSecond, self.stepSecond)
                    orderID = stepOrder.parentID                
                    self.orderDict['orderShortSet'].add(orderID)
                    self.orderLastList.append(orderID)
                    # 获取op对象，设置最长持有时间
                    op = self._orderPacks[orderID]
                    self.setConditionalClose(op, self.holdTime, self.expectReturn)                                   

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        # op = self._orderPacks[order.vtOrderID]
        # if not self.isFake(op):
        #     if order.status == STATUS_UNKNOWN:
        #         self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
        #                 % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        #     if order.status == STATUS_REJECTED:
        #         self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
        #                 % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
        #     if order.thisTradedVolume != 0:
        #         content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s, tradedVolume:%s'%\
        #                 (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price_avg, order.tradedVolume)
        #         # self.mail(content)
        self.setStop(order)

    def setStop(self, order):
        op = self._orderPacks.get(order.vtOrderID, None)
        # 判断是否该策略下的开仓
        if op:
            if order.offset == constant.OFFSET_OPEN:
                # 如果没有加过仓就设置初始的止损止盈
                if order.price_avg!=0 and self.nPos==0:
                    slGap = order.price_avg*self.stopLossPct
                    tpGap = order.price_avg*self.takeProfitPct
                    if order.direction == constant.DIRECTION_LONG:
                        if op.vtOrderID in self.orderDict['orderLongSet']:
                            self.setAutoExit(op, (order.price_avg-slGap), order.price_avg+tpGap)
                            op.info['slGap'] = slGap
                            self.globalStatus['orderLongGap'] = {'SL': order.price_avg-slGap, 'TP': order.price_avg+tpGap}
                            ##print('setAutoExit---long')
                    elif order.direction == constant.DIRECTION_SHORT:
                        if op.vtOrderID in self.orderDict['orderShortSet']:
                            self.setAutoExit(op, (order.price_avg+slGap), order.price_avg-tpGap)
                            op.info['slGap'] = slGap                            
                            self.globalStatus['orderFirstShort'] = {'SL': order.price_avg+slGap, 'TP': order.price_avg-tpGap}

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        pass

    def onStopOrder(self, so):
        pass