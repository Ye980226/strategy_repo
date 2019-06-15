from vnpy.trader.vtConstant import *
from vnpy.trader.utils.templates.orderTemplate import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from fiveCandleCode import candlestick
from volumeClass import volumeIndicator

########################################################################
class StrategyDoubleBarV2(OrderTemplate):
    className = 'strategyTest'
    author = 'zong'
    
    ### 参数列表
    paramList = [
        'symbolList',
        'posSize',
        'candleTypes',      # 一个list，里面存储需要使用的蜡烛图数
        'candlePeriods',    # 一个list，里面存储对应的蜡烛图的周期
        'secondMove',       # 第二张单放置的位置
        'holdmins',         # 最大持仓时间
        'takeProfit',       # 百分比止盈
        'firstmove',        # 移动止损的第一单位置
        'stopLoss',         # 百分比止损

        ### 计算doubleBar的参数
        'doubleBarShrink1',
        'doubleBarShrink2',

        ### 计算volumeSpike的参数
        'volumeNperiod',
        'volumeStdMultuper',

        ### 注册bar事件推送
        'timeframeMap'
    ]


    # 同步列表
    syncList = ['posDict', 'eveningDict']   

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.symbol = setting['symbolList'][0]
        ### 创建空的字典
        self.orderDict = {}
        self.lastKlineTime = {
            i:None for i in self.timeframeMap
        }

    # ----------------------------------------------------------------------
    def perpare_date(self):
        """
        注册bar事件，不需要特别推送，但需要获得对应的k线
        """
        for timeframe in self.timeframeMap:
            self.registerOnBar(self.symbol,timeframe,None)

    # --------------------------------------------------------------------
    def barPrepared(self, period):
        """
        判断是否产生了个新bar——有新bar则进行信号计算
        """
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("%s, am is not inited:%s" % (self.symbol,period))
            return False, None
        if self.lastKlineTime[period] is None or am.datetime[-1] > self.lastKlineTime[period]:
            return True, am
        else:
            return False, None

    # --------------------------------------------------------------------
    def updateLastKlineTime(self):
        """更新K线时间"""
        for period in self.timeframeMap:
            self.lastKlineTime[period] = self.getArrayManager(self.symbol, period).datetime[-1]


    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""

        if len(self.candleTypes)!=len(self.candlePeriods):
            raise Exception('指定的蜡烛图形态和指定的周期数目不一致')
        
        for candlePeriod in self.candlePeriods:
            if candlePeriod not in self.timeframeMap:
                raise Exception('请在ctaSetting-timeframeMap中指定需要注册的k线周期',candlePeriod)
        self.setArrayManagerSize(200)
        self.perpare_date()
        self.writeCtaLog(u'策略初始化')

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
    
    # ---------------------------------------------------------------------
    def on10sBar(self,bar):
        """
        实盘中在10秒bar里面洗价
        """
        self.checkOnPeriodStart(bar)
        #--------------------------------------------
        self.delOrderID() 
        self.writeCtaLog(str(self.orderDict))
        # -------------------------------------------
        self.checkOnPeriodEnd(bar)

    # ------------------------------------------------------------------------
    def delOrderID(self):
        """
        从self.OrderDict中删除已经完成的订单
        """
        for vtOrderID in list(self.orderDict):
            op = self._orderPacks[vtOrderID]
            if self.orderClosed(op):
                del self.orderDict[vtOrderID]

    # --------------------------------------------------------------------
    def onBar(self,bar):
        super().onBar(bar)
        if self.getEngineType() == 'backtesting':
            self.checkOnPeriodStart(bar)
            #--------------------------------------------
            self.delOrderID() 
            # -------------------------------------------
            self.checkOnPeriodEnd(bar)
        
        #### 执行策略逻辑
        self.strategy(bar)

    # -------------------------------------------------------------------
    def possitionCheck(self,opDict, buyMax=1, shortMax=1):
        """
        用于控制最大持仓数量
        """
        buy ,short = True, True
        buyNum, shortNum = 0, 0
        if len(opDict) == 0:
            pass
        else:
            for vtOrderID in opDict:
                op = self._orderPacks.get(vtOrderID, None)
                if op:
                    if op.order.direction == DIRECTION_LONG:
                        buyNum += op.order.tradedVolume
                    else:
                        shortNum += op.order.tradedVolume
            if buyNum+1 >= buyMax:
                buy = False            
            if shortNum+1 >= shortMax:
                short = False
        return buy, short  
 
    # ---------------------------------------------------------------------
    def strategy(self,bar):
        """
        策略逻辑主体，设置指标计算，信号组装，环境判断和下单
        """
        #### 根据出场信号出场
        exitSignal = self.exitSignal(bar)
        self.exitOrder(exitSignal,bar)
        #### 移动止损
        # self.moveStopLoss(bar)
        entrySignal = self.entrySignal(bar)
        ### 为了方便使用不同的了蜡烛图，这里返回的entrySignal是一个DICT
        self.entryOrder(entrySignal,bar)
        self.updateLastKlineTime()


    # -------------------------------------------------------------------
    def moveStopLoss(self, bar):
        for vtOrderID in self.orderDict:
            op = self._orderPacks[vtOrderID]
            price = self.orderDict[vtOrderID]['price']
            firstmove = self.orderDict[vtOrderID]['firstmove']
            if self.isAutoExit(op):
                oldsl = op.info[AutoExitInfo.TYPE].stoploss
                if op.order.direction == DIRECTION_LONG  \
                and bar.high/price-1>firstmove:
                    if bar.high*(1-self.takeProfit) > oldsl:
                        self.setAutoExit(op,bar.high*(1-self.takeProfit))
                elif op.order.direction == DIRECTION_SHORT \
                and bar.low/price-1<-firstmove:
                    if bar.low*(1+self.takeProfit) < oldsl:
                        self.setAutoExit(op,bar.low*(1+self.takeProfit))

    # --------------------------------------------------------------------
    def exitSignal(self,bar):
        """平仓信号"""
        return False

    # ---------------------------------------------------------------------
    def exitOrder(self,exitSignal,bar):
        """"平仓"""
        pass

    # ----------------------------------------------------------------------
    def entrySignal(self,bar):
        """计算信号"""
        am1min = self.getArrayManager(bar.vtSymbol,'1m')
        entrySignal = {}
        for candleType, candlePeriod in zip(self.candleTypes, self.candlePeriods):
            TF, am = self.barPrepared(candlePeriod)
            signal = 0
            if TF:
                #### cambridgehock 信号
                cd = candlestick(am.open, am.high, am.low, am.close)
                if cd.checkCandle(2):  ### 确保至少有两根已完成的k线才进入信号判断阶段
                    signal1 = getattr(cd, candleType)(self.doubleBarShrink1,self.doubleBarShrink2)
              
                ### volumeSpike 信号
                vi = volumeIndicator(am.open, am.high, am.low, am.close, am.volume)
                signal3 = True if vi.volumeSpike(self.volumeNperiod,self.volumeStdMultuper)[-1] else False
                
                ### 如果最近的一根bar特別深，同方向不近
                if am1min.close[-1]/am1min.open[-1] - 1 > 0.01 and signal1 > 0:
                    signal1 = 0
                elif am1min.close[-1]/am1min.open[-1] - 1 < -0.01 and signal1 < 0:
                    signal1 = 0 

                ### 最终确立signal
                signal = signal1 if signal3 else 0

            entrySignal[candleType] = signal  ## 记录signal结果用于交易
        return entrySignal

    # ------------------------------------------------------------------------
    def entryOrder(self, entrySignal, bar):
        """根据entrySignal里的信号进行交易"""
        am15 = self.getArrayManager(bar.vtSymbol, '15m')
        agap = abs(am15.close[-1]-am15.open[-1])

        if self.getEngineType() == 'trading':
            volume = self.posSize
        else:
            volume = self.posSize/bar.close

        buy, short = self.possitionCheck(self.orderDict)

        for candleType, signal in entrySignal.items():
            if signal == 1 and buy:
                self.writeCtaLog('%s find a buy signal lets buy it'%candleType)
                self.sendbuyOrder(bar,bar.close,volume,1,10)
                if agap*self.secondMove/bar.close > 0.005:
                    self.sendbuyOrder(bar,bar.close-agap*self.secondMove,volume,20)
            elif signal == 2 and buy:
                self.writeCtaLog('%s find a buy signal lets buy it_less'%candleType)
                self.sendbuyOrder(bar,bar.close-agap*self.secondMove,volume,20)
            elif signal == 3 and buy:
                self.writeCtaLog('%s find a reverse buy signal lets buy it'%candleType)
                self.sendbuyOrder(bar,bar.close,volume,1,10)                
            elif signal == -1 and short:
                self.writeCtaLog('%s find a short signal lets short it'%candleType)
                self.sendShortOrder(bar,bar.close,volume,1,10)
                if agap*self.secondMove/bar.close > 0.005:
                    self.sendShortOrder(bar,bar.close+agap*self.secondMove,volume,20)
            elif signal == -2 and short:
                self.writeCtaLog('%s find a short signal lets short it_less'%candleType)
                self.sendShortOrder(bar,bar.close+agap*self.secondMove,volume,20)               
            elif signal == -3 and short:
                self.writeCtaLog('%s find a reverse short signal lets short it'%candleType)
                self.sendShortOrder(bar,bar.close,volume,1,10)                


    # ----------------------------------------------------------
    def sendbuyOrder(self,bar,price,volume,waitmins,market=False):
        """发出买单并记录进入orderDict"""
        if not market:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, 
                    bar.vtSymbol, price,volume,60*waitmins)  
        else:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, 
                    bar.vtSymbol, price*1.01,volume,60*waitmins)           
        for vtOrderID in tlo.vtOrderIDs:
            op = self._orderPacks[vtOrderID]
            self.setConditionalClose(op,self.holdmins*60,None)
            self.setAutoExit(op,price*(1-self.stopLoss),price*(1+self.takeProfit))
            # self.setAutoExit(op,price*(1-self.stopLoss))
            self.orderDict[vtOrderID] = {
                'price':price,
                'firstmove':self.firstmove,
                'datetime':bar.datetime
            }
    
    # ----------------------------------------------------------
    def sendShortOrder(self,bar,price,volume,waitmins,market=False):
        """发出卖单并进入orderDict"""
        if not market:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, 
                    bar.vtSymbol, price,volume,60*waitmins) 
        else:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, 
                    bar.vtSymbol, price*0.99,volume,60*waitmins)             
        for vtOrderID in tlo.vtOrderIDs:
            op = self._orderPacks[vtOrderID]
            self.setConditionalClose(op,self.holdmins*60,None)
            self.setAutoExit(op,price*(1+self.stopLoss),price*(1-self.takeProfit))
            # self.setAutoExit(op,price*(1+self.stopLoss))
            self.orderDict[vtOrderID] = {
                'price':price,
                'firstmove':self.firstmove,
                'datetime':bar.datetime
            }
    
    # -------------------------------------------------------------
    def onOrder(self,order):
        super().onOrder(order)
        self.writeCtaLog('order.vtOrderID:%s, order.direction:%s, order.offset:%s, order.status:%s'%(
            order.vtOrderID, order.direction, order.offset, order.status
        ))

    # # ----------------------------------------------------------
    # def onTrade(self,trade):
    #     super().onTrade(trade)
    #     if trade.vtOrderID in self.orderDict:
    #         self.orderDict[trade.vtOrderID]['price'] = trade.price
    #         op = self._orderPacks[trade.vtOrderID]
    #         if trade.direction == DIRECTION_LONG:
    #             self.setAutoExit(op, trade.price*(1-self.stopLoss),trade.price*(1+self.takeProfit))
    #         else:
    #             self.setAutoExit(op, trade.price*(1+self.stopLoss),trade.price*(1-self.takeProfit))
       