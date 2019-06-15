import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time
from vnpy.trader.utils.templates.orderTemplate import *  
from diverence import DiverGenceGet as dg


'''
 #####
2019年2月15日 10:25:29
每当价格按照理想的方向移动self.addPercent，对应的止损也移动self.addPercent

2019年2月19日 15:54:11
过滤掉最近有极端行情的bar

2019年2月25日 09:03:18
try sigmal MA period change by atr
'''

########################################################################
class StrategyADX_macd(OrderTemplate):
    
    className = 'StrategyADX_macd'
    author = 'unknown author'

    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    paramList = [
        "symbolList",
        "posSize",
        "addTick",
        "miniTick",
        ########## DI_macd信号指标参数 ###########
        "macdPeriod",
        "fastPeriod",
        "fastMaType",
        "slowPeriod",
        "slowMaType",
        "signalPeriod",
        "signalMaType",
        "lagPeriod",
        "minPeriod",
        "maxPeriod",
        ########### 过滤条件参数 ############
        "ADXPeriod",
        "ADXpara",
        "ADXshield_up",
        "ADXshield_down",
        ########### 风控参数 #############
        "addPercent",  # 移动止损
        "stopLoss",    # 固定止损
        "maxPos",     
        "timeStopLoss",  #时间止损
        "signalWait",
        ####### 周期函数 ###3
        "timeframeMap"  
    ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        print(str(setting))
        self.writeCtaLog(str(setting))
        self.symbol = self.symbolList[0]

        ### 从setting中读取adx参数
        self.adxPara = {
            'ADXpara':setting['ADXpara'],
            'ADXshield_up':setting['ADXshield_up'],
            'ADXshield_down':setting['ADXshield_down']
        }
        self.buyClsoe, self.shortClose = datetime(2000,1,1), datetime(2000,1,1)
        ### 从setting中读取macd参数
        self.macdPara1 = {
            'fastPeriod':setting['fastPeriod'],
            'fastMaType':setting['fastMaType'],
            'slowPeriod':setting['slowPeriod'],
            'slowMaType':setting['slowMaType'],
            'signalPeriod':setting['signalPeriod'],
            'signalMaType':setting['signalMaType'],
            'lagPeriod':setting['lagPeriod'],
            'minPeriod':setting['minPeriod'],
            'maxPeriod':setting['maxPeriod']
        }

        ### 内部存贮订单并管理的字典
        self.orderDict = {}
        self.lastKlineTime = {
            i:None for i in self.timeframeMap
        }

        #### 给每个指标绑定对应的bar频率 ###
        self.barPeriodMap = {
            'macdPeriod':self.macdPeriod,
            'ADXPeriod':self.ADXPeriod
        }
        ### 生成对应的全局变量
        self.adxsignal = False


        ##### 用于画图分析 ######
        self.dilog = {
            'datetime':[],
            'macd':[],
            'macdSignal':[]
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
            self.writeCtaLog("am is not inited:%s" % (period,))
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
                    self.buyClsoe = bar.datetime
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
            timeStopLoss = self.timeStopLoss + min(op.info['addMessage']['internal'],60)*15
            if op.order.direction == DIRECTION_LONG:
                if (bar.high-price)/price > addPercent:  ### 这个判断用于防止止损比addPercent大时意外移动的情况
                    if bar.close-addPercent*price > exitPrice:
                        self.writeCtaLog('多头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
                        self.setAutoExit(op,stoploss=bar.close)
                        self.setConditionalClose(op,int(timeStopLoss*60),None)  ### 移动止损后重新计算时间止损
            else:
                if (bar.low-price)/price < -addPercent:
                    if bar.close+addPercent*price < exitPrice:
                        self.writeCtaLog('空头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
                        self.setAutoExit(op,stoploss=bar.close)
                        self.setConditionalClose(op,int(timeStopLoss*60),None) 

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
        #### 执行策略逻辑
        self.strategy(bar)
        self.delOrderID(bar) 
        self.moveStopLoss(bar,self.addPercent)   
        buypos, shortpos = self.getPos()
        self.writeCtaLog('每分钟打印仓位, 多头持仓:%s, 空头持仓:%s'%(buypos,shortpos))             
        if self.getEngineType() == 'backtesting':
            self.checkOnPeriodStart(bar)
            # -------------------------------------------
            self.checkOnPeriodEnd(bar)
           
    # ---------------------------------------------------------------------
    def strategy(self,bar):
        """
        策略逻辑主体，设置指标计算，信号组装，环境判断和下单
        """
        #### 根据出场信号出场
        # exitSignal = self.exitSignal(bar)
        # self.exitOrder(exitSignal,bar)
        # entrySignal,internal = self.entrySignal(bar)
        # self.entryOrder(entrySignal,bar,internal)
        self.updateLastKlineTime()

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
        """计算发单信号"""
        
        signal,internal = 0, 0
        ### 按照ADXPeriod获得过滤结果
        TF, amfilter = self.barPrepared(self.ADXPeriod)
        if TF:
            self.adxsignal, _ = dg.ADXget(self,amfilter,self.adxPara)        
        
        #### 按照macdPeriod获得信号结果
        TF, amSignal = self.barPrepared(self.macdPeriod)
        if TF:
            signal, internal,macd,macdSignal = dg.MACDget(self,amSignal,self.macdPara1)
            if internal <= 20:  ## 抛弃internal过小的信号
                signal = 0
            ### 记录用于画图的数据 ###
            self.dilog['datetime'].append(bar.datetime)
            self.dilog['macd'].append(macd[-1])
            self.dilog['macdSignal'].append(macdSignal[-1])  

        ### 检查信号和仓位判断能否发单
        buy1, short1 = self.signalWaitCheck(self.orderDict,bar.datetime+timedelta(minutes=15),self.signalWait)
        buy2, short2 = self.possitionCheck(self.orderDict,self.maxPos,self.maxPos)
        
        ### 根据signal和buy1buy2等判断能否发单
        if signal == -1 and short1 and short2 and self.adxsignal \
        and (bar.datetime-self.buyClsoe).total_seconds()/60 > 5:
            pass
        elif signal == 1 and buy1 and buy2 and self.adxsignal \
        and (bar.datetime-self.shortClose).total_seconds()/60 > 5:
            pass
        else:
            signal = 0        

        if signal != 0:
            self.writeCtaLog('singal:%s发现信号发出订单'%signal)

        return signal, internal      


    # ------------------------------------------------------------
    def entryOrder(self,signal,bar,internal):
        """
        得到信号后判断能否下单
        """
        if self.getEngineType() == 'trading':
            volume = self.posSize
        else:
            volume = self.posSize/bar.close

        #### 根据信号下单 ###
        if signal == 1:
            self.writeCtaLog(u'%s时间判断顶背离，发出short信号,internal:%s'%(bar.datetime,internal))
            # 使用timelimiterOrder下单
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT,bar.vtSymbol,
            bar.close-self.addTick*self.miniTick,volume, 120)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                #### 向info中添加addMessage帮助后续操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'short','move':0,
                'price':bar.close,'exitPrice':bar.close*(1+self.stopLoss),'internal':internal}
                self.orderDict[vtOrderID] = {}
                self.writeCtaLog('拟定的最大持仓时间:%s'%(int(self.timeStopLoss+min(60,internal))*60))
                self.setConditionalClose(op,int(self.timeStopLoss+15*min(60,internal))*60,None)                
            
        elif signal == -1:
            self.writeCtaLog(u'%s时间判断底背离，发出buy信号,internal:%s'%(bar.datetime,internal))
            # 使用timelimiterOrder下单
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY,bar.vtSymbol,
            bar.close+self.addTick*self.miniTick,volume,120)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                ### 向info中添加addMessage帮助后续便捷操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'buy','move':0,
                'price':bar.close,'exitPrice':bar.close*(1-self.stopLoss),'internal':internal}
                self.orderDict[vtOrderID] =  {}
                self.writeCtaLog('拟定的最大持仓时间:%s'%(int(self.timeStopLoss+15*min(60,internal))*60))
                self.setConditionalClose(op,int(self.timeStopLoss+min(60,internal))*60,None)

    # ----------------------------------------------------------------------
    def on30MinBar(self, bar):

        am30 = self.getArrayManager(bar.vtSymbol, "30m")
        if not am30.inited:
            return
        self.adxsignal, self.adx = dg.ADXget(self,am30,self.adxPara) 

    # ----------------------------------------------------------------------
    def onOrder(self,order):
        super().onOrder(order)
        self.writeCtaLog('%s发出订单:%s,status:%s'%(order.orderTime,order.vtOrderID, order.status))
        pass
 

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        super().onTrade(trade)
        self.writeCtaLog('发生了成交，方向：%s, 开平:%s, 成交价:%s'%(trade.direction, trade.offset, trade.price))
        # self.mail('发生了成交，方向：%s, 开平:%s, 成交价:%s, 成交量:%s'%(trade.direction, trade.offset, trade.price, trade.volume))
        
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
      
