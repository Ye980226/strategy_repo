import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time
from doubleBoll import doubleBoll
db = doubleBoll()
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase

'''
使用移动止损的办法控制出场
2019年2月15日 10:25:29
每当价格按照理想的方向移动self.addPercent，对应的止损也移动self.addPercent

2019年2月19日 15:54:11
过滤掉最近有极端行情的bar
'''

########################################################################
class StrategyBoll(OrderTemplate):
    
    className = 'StrategyBoll'
    author = 'unknown author'

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']
    # 参数列表，保存了参数的名称
    paramList = [
                "symbolList",
                "posSize",
                "miniTick",
                "addTick",
                "maxPos", 
                #### 计算指标的参数
                "BollBar",
                "BollPeriod",
                "EMAPeriod",
                "pctPeriod",
                #### 生成信号的阈值
                "divShield",
                "pctUp",
                "pctDown",
                ### 风控参数
                "addPercent",
                "stopLoss",
                "timeStopLoss", 
                "signalWait",
                ### 过滤条件参数，好像没什么用 
                "atrBar", 
                "atrPeriod",
                "atrShield"
                ####
                "timeframeMap"
                ]
    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        print(setting) 
        self.writeCtaLog(str(setting))

        ### 从setting中读取adx参数
        self.symbol1 = setting['symbolList'][0]
        self.symbol2 = setting['symbolList'][1]
        self.timeframeMap = setting['timeframeMap']
        self.atrShield = setting['atrShield']
        ### 从setting中para参数
        self.para = {
            'Bollperiod':setting['BollPeriod'],
            'EMAperiod':setting['EMAPeriod']
        }
    
        ###
        self.orderDict = {}
        self.buyClose , self.shortClose = datetime(2000,1,1), datetime(2000,1,1)
        self.diOver = 0
        ### 输出画图
        self.matlog = {
            'datetime':[],
            'divergence':[],
            'pct':[]
        }

    # ----------------------------------------------------------------------
    def perpare_date(self):
        """
        注册bar事件，不需要特别推送，但需要获得对应的k线
        """
        for timeframe in self.timeframeMap:
            self.registerOnBar(self.symbol1,timeframe,None)
            self.registerOnBar(self.symbol2,timeframe,None)
    
    # --------------------------------------------------------------------
    def arrayPerpare(self, symbol,period):
        """
        判断是否产生了个新bar——有新bar则进行信号计算
        """
        am = self.getArrayManager(symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False, None
        else:
            return True, am


    # ----------------------------------------------------------------------
    def signalWaitCheck(self,orderDict,datetime,signalWait):
        """
        用于过滤相邻时间不超过signalWait的同方向信号
        """
        buy, short = True, True
        if len(orderDict) == 0:
            pass
        else:
            for vtOrderID in orderDict:
                op = self._orderPacks.get(vtOrderID, None)
                if op:
                    if op.order.direction == DIRECTION_LONG and (datetime-op.order.orderDatetime).total_seconds()/60 < signalWait:
                        buy = False
                    elif op.order.direction == DIRECTION_SHORT and (datetime-op.order.orderDatetime).total_seconds()/60 < signalWait:
                        short = False 
        return buy, short 
    
    # -------------------------------------------------------------------
    def possitionCheck(self,orderDict, buyMax=1, shortMax=1):
        """
        用于控制最大持仓数量
        """
        buy ,short = True, True
        buyNum, shortNum = 0, 0
        if len(orderDict) == 0:
            pass
        else:
            for vtOrderID in orderDict:
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

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.setArrayManagerSize(1000)
        self.perpare_date()
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
        super().onTick(tick)
        pass
    
    # ---------------------------------------------------------------------
    def on10sBar(self,bar):
        """
        实盘中在10秒bar里面洗价
        """
        if bar.vtSymbol == self.symbol2:
            return        
        self.checkOnPeriodStart(bar)
        #--------------------------------------------
        self.moveStopLoss(bar,self.addPercent)
        # -------------------------------------------
        self.checkOnPeriodEnd(bar)

    # ------------------------------------------------------------------------
    def delOrderID(self,bar):
        """
        从self.OrderDict中删除已经完成的订单
        """
        for vtOrderID in list(self.orderDict):
            op = self._orderPacks[vtOrderID]
            if self.orderClosed(op):
                if op.order.direction == DIRECTION_LONG:
                    self.buyClose = bar.datetime
                else:
                    self.shortClose = bar.datetime
                del self.orderDict[vtOrderID]

    # ------------------------------------------------------------------------
    def moveStopLoss(self,bar,addPercent):
        """
        用于判断移动止损，移动方法如下：
        以多头为例，当观测到最近一个bar的最高价相比起成交价已经高出addPercent倍以close作为止损价格
        """
        for vtOrderID in list(self.orderDict):
            op = self._orderPacks.get(vtOrderID, None)
            if not op:
                continue 
            price = op.info['addMessage']['price']
            exitPrice = op.info['addMessage']['exitPrice']
            if op.order.direction == DIRECTION_LONG:
                if (bar.high-price)/price > addPercent:  ### 这个判断用于防止止损比addPercent大时意外移动的情况
                    if bar.close-addPercent*price > exitPrice:
                        self.writeCtaLog('多头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
                        self.setAutoExit(op,stoploss=bar.close)
                        self.setConditionalClose(op,self.timeStopLoss*60,None)  ### 移动止损后重新计算时间止损
            else:
                if (bar.low-price)/price < -addPercent:
                    if bar.close+addPercent*price < exitPrice:
                        self.writeCtaLog('空头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
                        self.setAutoExit(op,stoploss=bar.close)
                        self.setConditionalClose(op,self.timeStopLoss*60,None) 

    # ----------------------------------------------------------------------
    def getPos(self):
        buypos, shortpos = 0, 0
        for vtOrderID in self.orderDict:
            op = self._orderPacks[vtOrderID]
            openVolume = op.order.tradedVolume
            closeVolume = self.orderClosedVolume(op)
            if op.order.direction == DIRECTION_LONG:
                buypos += openVolume-closeVolume
            else:
                shortpos += openVolume-closeVolume
        return buypos, shortpos

    # --------------------------------------------------------------------
    def onBar(self,bar):
        super().onBar(bar)
        
        if bar.vtSymbol == self.symbol2:
            return

        #### 执行策略逻辑
        self.strategy(bar)       
        self.delOrderID(bar) 
        self.moveStopLoss(bar,self.addPercent)
        buypos, shortpos = self.getPos()
        self.writeCtaLog('每分钟打印仓位, 多头持仓:%s, 空头持仓:%s'%(buypos,shortpos))

        if self.getEngineType() == 'backtesting':
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)

    # ---------------------------------------------------------------------
    def strategy(self,bar):
        """
        策略逻辑主体，设置指标计算，信号组装，环境判断和下单
        """
        #### 根据出场信号出场
        entrySignal = self.entrySignal(bar)
        self.entryOrder(entrySignal,bar)
        ### 多的入场信号作为空的出场信号
        exitSignal = entrySignal  
        self.exitOrder(exitSignal,bar)
        
    # --------------------------------------------------------------------
    def exitOrder(self,signal,bar):
        """平仓信号"""
        ### 根据信号下单 ###
        if signal == -1:
            #### 下单之前要先平掉反向的仓位
            for orderID in list(self.orderDict):
                op = self._orderPacks[orderID]
                if op.order.direction == DIRECTION_LONG:
                    self.composoryClose(op)
                    self.writeCtaLog('策略判断出现short信号，平掉持有的long仓位')
            
        elif signal == 1:
            #### 下单之前要先平掉反向的仓位
            for orderID in list(self.orderDict):
                op = self._orderPacks[orderID]
                if op.order.direction == DIRECTION_SHORT:
                    self.composoryClose(op)
                    self.writeCtaLog('策略判断出现buy信号，平掉持有的short仓位')            

    # ----------------------------------------------------------------------
    def entrySignal(self,bar):
        """计算发单信号"""
        signal = 0
        ### 按照信号过滤
        TF1, am1 = self.arrayPerpare(self.symbol1,self.BollBar)
        TF2, am2 = self.arrayPerpare(self.symbol2,self.BollBar)
        TF3, amAtr = self.arrayPerpare(self.symbol1,self.atrBar)

        if TF1 and TF2 and TF3:
            ### 判断两个amDict的时间是否对齐
            if am1.datetime[-1]==am2.datetime[-1]:  
                divergence = db.BollingerBand_Divergence(am1,am2,self.para)
                ### 对因为数据缺失导致的异常值进行处理，空值赋值为0，过大或过小的值进行缩尾
                divergence[np.isnan(divergence)] = 0
                divergence[divergence>100]=100
                divergence[divergence<-100]=100                
                pct = ta.ROCP(am1.close,self.pctPeriod)[-1]
                atr1 = ta.ATR(amAtr.high,amAtr.low,amAtr.close,self.atrPeriod)[-1]

                self.matlog['datetime'].append(bar.datetime)
                self.matlog['divergence'].append(divergence[-1])
                self.matlog['pct'].append(pct)

                if self.diOver==1 and divergence[-1] < 0:
                    self.diOver = 0
                elif self.diOver==-1 and divergence[-1]>0:
                    self.diOver = 0

                if divergence[-1]>self.divShield and divergence[-1]<divergence[-2] and \
                self.diOver == 0:
                    self.diOver = 1
                    if pct > self.pctDown and pct < self.pctUp:
                        signal = 1
                    elif pct < -self.pctDown:
                        signal = -1
                    else:
                        signal = 0
                elif divergence[-1]<-self.divShield and divergence[-1]>divergence[-2] and \
                self.diOver == 0 :
                    self.diOver = -1
                    if pct > self.pctDown:
                        signal = -1
                    elif pct < -self.pctDown and pct > -self.pctUp:
                        signal = 1
                    else:
                        signal = 0
                else:
                    signal = 0


                #### 过滤掉同方向的信号距离上一个不足signalWait时间 ####
                buy1, short1 = self.signalWaitCheck(self.orderDict,bar.datetime+timedelta(minutes=15),self.signalWait)
                #### 检查已有的持仓
                buy2, short2 = self.possitionCheck(self.orderDict,self.maxPos,self.maxPos)

                if signal == 1 and buy1 and buy2 and atr1<self.atrShield \
                and (bar.datetime-self.buyClose).total_seconds()/60 > 30:
                    pass
                elif signal == -1 and short1 and short2 and atr1<self.atrShield \
                and (bar.datetime-self.shortClose).total_seconds()/60 > 30:
                    pass
                else:
                    signal = 0

                if signal != 0:
                    self.writeCtaLog('singal:%s发现信号发出订单'%signal)                
                
        return signal
            

    # -----------------------------------------------------------------------
    def entryOrder(self,signal,bar):
        """
        得到信号后判断能否下单
        """
        if self.getEngineType() == 'trading':
            volume = self.posSize
        else:
            volume = self.posSize/bar.close
        
        ### 根据信号下单 ###
        if signal == -1:
            #### 使用timelimiterOrder下单
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT,bar.vtSymbol,
            bar.close-self.addTick*self.miniTick,volume, 1200)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                ### 向info中添加addMessage帮助后续便捷操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'short','move':0,
                'price':bar.close,'exitPrice':bar.close*(1+self.stopLoss)}
                self.setConditionalClose(op,self.timeStopLoss*60,None)
                self.orderDict[vtOrderID] = True

        elif signal == 1:
         
            ### 使用timelimierOrder下单
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY,bar.vtSymbol,
            bar.close+self.addTick*self.miniTick,volume,1200)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                ### 向info中添加addMessage帮助后续便捷操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'buy','move':0,
                'price':bar.close,'exitPrice':bar.close*(1-self.stopLoss)}
                self.setConditionalClose(op,self.timeStopLoss*60,None)
                self.orderDict[vtOrderID] =  True

    # -----------------------------------------------------------------------
    def onOrder(self,order):
        super().onOrder(order)
        self.writeCtaLog(f'onOrderLog,orderID:{order.vtSymbol}{order.vtOrderID}{order.status}{order.totalVolume}')
        
    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        super().onTrade(trade)
        self.writeCtaLog('发生了成交, id:%s，方向：%s, 开平:%s, 成交价:%s'%(trade.vtOrderID, trade.direction, trade.offset, trade.price))
        # self.mail('发生了成交, id:%s，方向：%s, 开平:%s, 成交价:%s, 成交量:%s'%(trade.vtOrderID, trade.direction, trade.offset, trade.price,trade.volume))
        self.writeCtaLog('onTrade现有的持仓:%s'%str(self.orderDict))

        ### 获得成交价
        if trade.vtOrderID in self.orderDict:
            op = self._orderPacks.get(trade.vtOrderID, None)
            if op:
                ### 绑定止盈和止损 
                if trade.direction == DIRECTION_LONG:
                    op.info['price'] = trade.price
                    op.info['exitPrice'] = (1-self.stopLoss)*trade.price
                    self.setAutoExit(op,stoploss=(1-self.stopLoss)*trade.price)
                    self.writeCtaLog('多头开仓, 止损价:%s'%((1-self.stopLoss)*trade.price))
                elif trade.direction == DIRECTION_SHORT:
                    op.info['price'] = trade.price
                    op.info['exitPrice'] = (1+self.stopLoss)*trade.price
                    self.setAutoExit(op,stoploss=(1+self.stopLoss)*trade.price)
                    self.writeCtaLog('空头开仓，止损价为%s'%((1+self.stopLoss)*trade.price))


    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass