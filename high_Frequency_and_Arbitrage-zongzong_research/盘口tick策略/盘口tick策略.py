# encoding: UTF-8

"""
盘口策略
观测到指标出现挂单
挂单超过10s立即撤单
成交后挂出止盈单，同时每个tick检查是否到达止损位置
发生一次止损之后一段时间内不进场
持仓超过1分钟的单全部平掉

需要传入的参数：

用于计算是否入场的指标（使用给定指标计算挂单方向和挂单价格）

挂单未成交时间长度: openTime
持仓最长时间: holdTime
止盈价格绝对值: takeProfit
止损价格绝对值: stopLoss

2018年11月14日 23:15:13  
新增发生一次止损后30分钟内同方向不再进场

2018年11月15日 10:06:17
新增对到期单的处理，记录原有的stopLoss价格，同时按照盘口挂限价单
经过self.timeAdd时间若未成交循环操作，直至全部成交/超过self.maxTimeAdd次数后按照市价出场

2018年11月15日 15:42:34
修改‘新增发生一次止损后30分钟内同方向不再进场’为‘新增发生x次止损后30分钟内同方向不再进场’

2018年11月16日 10:28:41
需要一个判断大波动结束了的指标，使用均线粘合
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
import numpy as np
import pandas as pd
import talib as ta
import time
from datetime import datetime
########################################################################
class TickBaseStrategy(CtaTemplate):
    """配对交易策略"""
    className = 'TickBaseStrategy'
    author = 'HFgroup'

    # 策略交易标的
    #symbolList = []                 # 初始化为空
    symbol = EMPTY_STRING

    # 策略变量
    posSize = 1
    waitCount = 0
    ### 记录表现 ####
    #### 从左往右分别是 止损出场次数，到期出场次数，止盈出场次数 ####
    longWin = [0,0,0]
    shortWin = [0,0,0]
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'longWin',
                 'shortWin']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TickBaseStrategy, self).__init__(ctaEngine, setting)
        self.posSize = setting['posSize']
        # 固定止盈和固定止损
        self.takeProfit = setting['takeProfit']
        self.stopLoss = setting['stopLoss']
        # 挂单位置
        self.gap = setting['gap']
        self.maxnumber = setting['maxnumber']
        # 过滤掉接下来多长时间的信号
        self.waitTime = setting['waitMins']
        # 是否使用出了固定时间不不开仓以外的其它信号
        self.otherSign = setting['otherSign']

    
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        
        # 读取交易品种  
        self.symbol = self.symbolList[0]   
        
        # list用于储存tick
        self.tickList = []


        ####################### 挂撤单逻辑需要用到的参数等 ######
        #挂撤单需要用到的各种字典
        self.sellOrderDict, self.coverOrderDict = {}, {}
        self.buyOrderDict , self.shortOrderDict = {}, {}
        # 控制可以挂出的最大单量
        self.Longcount, self.Shortcount = 0, 0
        # 记录挂单总数和仓位
        self.Longcount , self.Shortcount = 0 ,0 
        # 挂单和持仓时间
        self.openTime, self.holdTime = 15,60
        # 到期出场挂单时间
        # self.timeAdd:持仓时间超过1分钟后按盘口价格出场的挂单等待时间， maxTimeAdd，最多重复挂几次
        self.timeAdd , self.maxTimeAdd = 5,2
        # 出现x次止损后同方向过滤掉接下来一段时间的信号
        self.buyLossMax, self.shortLossMax = 2, 2
        # 记录各仓位连续止损的次数
        self.buyLossNum, self.shortLossNum = 0, 0
        self.waitTo = False
        self.lastTradeTime = datetime.now()
        # 生成1分钟bar推送
        self.generateBarDict(self.onBar,size=2000)
        # 生成1s高频bar，不用于updateBar，仅用于2s一次触发逻辑
        self.generateHFBar(1)

        engine = self.getEngineType()
        # 回测读取数据
        if engine == 'trading':
            ### 实盘从交易所读取数据
            kline = self.loadHistoryBar(self.symbol, '1min', 2000)
            ### 将读取的数据填入amDict
            for bar in kline:
                self.amDict[self.symbol].updateBar(bar)
        else:
            self.initBacktesingData()

        self.putEvent()
    
    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)  
        # self.file = open('tickData.txt','a')  
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        # self.file.close()
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        
        # #######################
        # avsum = tick.askVolume1+tick.askVolume2+tick.askVolume3
        # bvsum = tick.bidVolume1+tick.bidVolume2+tick.bidVolume3
        # self.file.write(u'datetime:%s,askPrice1:%s, askPrice3:%s,bidPrice1:%s,bidPrice3:%s,lastPrice:%s,avsum:%s, bvsum:%s \n'
        # %(tick.datetime,tick.askPrice1,tick.askPrice3,tick.bidPrice1,tick.bidPrice3,tick.lastPrice,avsum,bvsum))
        # #######################

        ### 生成对应的bar并推送
        self.bgDict[tick.vtSymbol].updateTick(tick)   
        self.tick = tick
        self.hfDict[tick.vtSymbol].updateHFBar(tick) 
   
        ### 记录计算买卖信号需要的数据 ###
        if tick.volumeChange == 0:
            self.tickList.append(tick)
        else:
            if tick.type == 'ask':
                self.lastAskTime = tick.datetime
            else:
                self.lastBidTime = tick.datetime
            return

        ### 保存tick到tickList中
        if len(self.tickList) < 10:
            self.lastAskTime,self.lastBidTime = tick.datetime,tick.datetime
            self.buyStopTime, self.shortStopTime = tick.datetime,tick.datetime
            return

        ################# 计算买卖信号 ##################
        thisTick = self.tickList[-1]
        lastTick = self.tickList[-2]
        
        if thisTick.askPrice1 > lastTick.askPrice3 and (tick.datetime-self.shortStopTime).total_seconds()/60>self.waitTime  and not self.waitTo:
        # if thisTick.askPrice1 > lastTick.askPrice3 and (tick.datetime-self.lastBidTime).total_seconds()<1 and (tick.datetime-self.shortStopTime).total_seconds()/60>30 and not self.waitTo:
            #### 进入short信号计算逻辑, 最后一个if是为了防止20015频繁挂撤单错误
            if lastTick.askVolume1 + lastTick.askVolume2 + lastTick.askVolume3 > 1000 and self.Shortcount < self.maxnumber and (tick.datetime-self.lastTradeTime).total_seconds()>2:
                shortPrice, shortVolume = thisTick.lastPrice+self.gap,self.posSize
                orderID = self.short(self.symbol,shortPrice,shortVolume)[0]
                self.shortOrderDict[orderID] = {'time':tick.datetime,'takeProfit':shortPrice-self.takeProfit,
                'stopLoss':shortPrice+self.stopLoss}
                self.writeCtaLog(u'发生信号发出订单:%s,short卖开,%s'%(orderID,shortPrice))
                self.Shortcount+=shortVolume                
           
        elif thisTick.bidPrice1 < lastTick.bidPrice3 and (tick.datetime-self.buyStopTime).total_seconds()/60>self.waitTime and not self.waitTo:
        # elif thisTick.askPrice1 > lastTick.askPrice3 and (tick.datetime-self.lastAskTime).total_seconds()<1 and (tick.datetime-self.buyStopTime).total_seconds()/60>30 and not self.waitTo:
            #### 进入buy信号计算逻辑, 最后一个if是为了防止20015频繁挂撤单错误
            if lastTick.bidVolume1 + lastTick.bidVolume2 + lastTick.bidVolume3 > 1000 and self.Longcount < self.maxnumber and (tick.datetime-self.lastTradeTime).total_seconds()>2:
                buyPrice, buyVolume = thisTick.lastPrice-self.gap,self.posSize
                orderID = self.buy(self.symbol,buyPrice,buyVolume)[0]
                self.buyOrderDict[orderID] = {'time':tick.datetime,'takeProfit':buyPrice+self.takeProfit,
                'stopLoss':buyPrice-self.stopLoss}
                self.writeCtaLog(u'发生信号发出订单:%s,buy买开,%s'%(orderID,buyPrice))
                self.Longcount+=buyVolume                
    
        self.putEvent()

    # ----------------------------------------------------------------------
    def onHFBar(self,bar):
        """收到高频（秒级）bar推送""" 
        # print('HFFFFFF',bar.datetime,len(self.tickList))
        # self.hfamDict[self.symbol].updateBar(bar)
        ####### 信号发出器：计算并判断是否挂单，输出挂单价格和指标 #######

        """
        buy = True, buyPrice = 买入价格, buyVolume = 买入手数
        short = True, shortPrice = 卖出价格, shortVolume = 卖出手数
        
        订单管理逻辑如下：
        当收到一个买信号，策略会首先判断当前仓位+未成交订单是否已到最大仓位，如果是，
        拒绝这次信号，否则按照信号挂出订单，同时记录订单号，发单时间，固定止盈价格和固定止损价格

        之后每隔HFBar策略会检查这张单的情况，对于未成交的订单，超过一段时间会撤销
        对于已成交的订单，策略会检查是否到达止损条件
        
        卖出信号类似
        """
       
        ################# 撤单逻辑 ######################
        for orderID in self.buyOrderDict:
            if (bar.datetime-self.buyOrderDict[orderID]['time']).total_seconds() > self.openTime:
                self.cancelOrder(orderID)
        for orderID in self.shortOrderDict:
            if (bar.datetime-self.shortOrderDict[orderID]['time']).total_seconds() > self.openTime:
                self.cancelOrder(orderID)

        
        ################# 固定止损和时间止损逻辑 ####################
        price = self.tick.lastPrice     #使用中间价还是上一个成交价进行止损处理是需要考虑的
        
        for orderID in self.sellOrderDict:
            if price < self.sellOrderDict[orderID]['stopLoss']:
                self.writeCtaLog(u'Oh no,多头止损触发,止损价:%s,当前价格:%s'%(self.sellOrderDict[orderID]['stopLoss'],price))
                self.sellOrderDict[orderID]['type'] = 'stopLoss'
                ######### 发生x次止损出场30分钟内不再进场
                self.buyLossNum += 1                
                if self.buyLossNum >= self.buyLossMax:
                    self.buyStopTime = self.tick.datetime
                    self.shortStopTime = self.tick.datetime
                    self.waitTo = self.otherSign
                self.cancelOrder(orderID)
            elif (bar.datetime-self.sellOrderDict[orderID]['time']).total_seconds() > self.sellOrderDict[orderID]['hold']:
                self.writeCtaLog(u'时间止损触发，开仓价格:%s,当前价格:%s'%(self.sellOrderDict[orderID]['price'],price))
                self.sellOrderDict[orderID]['type'] = 'timeout'
                self.cancelOrder(orderID)
        
        for orderID in self.coverOrderDict:
            if price > self.coverOrderDict[orderID]['stopLoss']:
                self.writeCtaLog(u'Oh no,空头止损触发,止损价:%s,当前价格:%s'%(self.coverOrderDict[orderID]['stopLoss'],price))
                self.coverOrderDict[orderID]['type'] = 'stopLoss'
                ######## 发生一次止损出场30分钟内不再进场
                self.shortLossNum += 1
                if self.shortLossNum >= self.shortLossMax:
                    self.shortStopTime = self.tick.datetime
                    self.buyStopTime = self.tick.datetime
                    self.waitTo = self.otherSign
                self.cancelOrder(orderID)
            elif (bar.datetime-self.coverOrderDict[orderID]['time']).total_seconds() > self.coverOrderDict[orderID]['hold']:
                self.writeCtaLog(u'时间止损触发，开仓价格:%s,当前价格:%s'%(self.coverOrderDict[orderID]['price'],price))
                self.coverOrderDict[orderID]['type'] = 'timeout'
                self.cancelOrder(orderID)
        
        self.putEvent()



    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.amDict[bar.vtSymbol].updateBar(bar) 
        # print(len(self.tickList,'tickkkkkkk'))
        ######## 定期清理tick列表 ######
        if len(self.tickList) > 2000:
            self.tickList = self.tickList[-1000:]
            self.writeCtaLog(u'仅保留最近1000个tick, I am still alive')
        ################################

        if self.waitTo:
            ## 根据均线的聚合情况判断波动是否已经结束
            dif = 0.005
            close = self.amDict[self.symbol].close
            ma5,ma20,ma30,ma60 = np.mean(close[-5:]),np.mean(close[-20:]),np.mean(close[-30:]),np.mean(close[-60:])
            if abs(ma5-ma20)<dif and abs(ma5-ma30)<dif and abs(ma5-ma60)<dif and abs(ma20-ma30)<dif and abs(ma20-ma60)<dif and abs(ma30-ma60)<dif:
                self.waitTo = False
                self.writeCtaLog(u'判断波动率恢复平稳，重新启动挂单')

        self.putEvent()


    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""   
        self.writeCtaLog(u'收到订单状态：%s, :status:%s, traded:%s, total:%s,order.price:%s'%(order.vtOrderID,order.status,order.tradedVolume,order.totalVolume,order.price)) 

        #### 对成交单，止损单和止盈单进行操作
        if order.status == STATUS_PARTTRADED:
            price = order.price
            volume = order.thisTradedVolume
            # 回测中没有order.thisTradedVolume，需要修改
            # volume = 1
            time = datetime.now()
            ##### 现在order.orderTime是一个空值     
            ### 开仓单成交了要立刻补上对应价格平仓单
            if order.vtOrderID in self.buyOrderDict:
                orderID = self.sell(self.symbol,self.buyOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.sellOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'stopLoss':self.buyOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                
            elif order.vtOrderID in self.shortOrderDict:
                orderID = self.cover(self.symbol,self.shortOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.coverOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'stopLoss':self.shortOrderDict[order.vtOrderID]['stopLoss'],'total':volume}

        
        elif order.status == STATUS_ALLTRADED:
            price = order.price
            volume = order.thisTradedVolume
            # 回测中没有order.thisTradedVolume，需要修改
            #  volume = 1
            time = datetime.now()
            ### 开仓单成交了要立刻补上对应价格平仓单
            if order.vtOrderID in self.buyOrderDict:
                orderID = self.sell(self.symbol,self.buyOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.sellOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'stopLoss':self.buyOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                ### 全部成交的订单要从字典里删除
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                orderID = self.cover(self.symbol,self.shortOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.coverOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'stopLoss':self.shortOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                ### 全部成交的订单要从字典里删除
                del self.shortOrderDict[order.vtOrderID]
            ### 止盈单成交了要记录
            elif order.vtOrderID in self.sellOrderDict:
                self.Longcount -= order.totalVolume
                self.longWin[2] += self.sellOrderDict[order.vtOrderID]['TimeOut']
                ## 只有TimeOut为1的才是止盈单，timeOut为0是时间止损单
                if self.sellOrderDict[order.vtOrderID]['TimeOut'] > 0:
                    self.writeCtaLog(u'多头止盈出场_%s，Oh Yeah'%order.vtOrderID)
                    self.buyLossNum = 0
                del self.sellOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.coverOrderDict:
                self.Shortcount -= order.totalVolume
                self.shortWin[2] += self.coverOrderDict[order.vtOrderID]['TimeOut']
                ## 只有TimeOut为1的才是止盈单，timeOut为0是时间止损单
                if self.coverOrderDict[order.vtOrderID]['TimeOut'] > 0:
                     self.writeCtaLog(u'空头止盈出场_%s，Oh Yeah'%order.vtOrderID)
                     self.shortLossNum = 0
                del self.coverOrderDict[order.vtOrderID]


        # 对已撤销单进行处理
        elif order.status == STATUS_CANCELLED:
            ## 撤销的是平仓单，进入价格止损或时间止损逻辑
            if order.vtOrderID in self.sellOrderDict:
                if self.sellOrderDict[order.vtOrderID]['type'] == 'stopLoss':
                    self.Longcount -= order.totalVolume - order.tradedVolume
                    self.sell(self.symbol,self.tick.lowerLimit+0.001,order.totalVolume-order.tradedVolume)
                    self.longWin[0] += 1
                # elif self.sellOrderDict[order.vtOrderID]['type'] == 'timeout':
                else:
                    ## 对timeout的订单进行处理, 按照盘口价格挂单,是否使用对手价值得进一步考虑
                    self.longWin[1] += self.sellOrderDict[order.vtOrderID]['TimeOut']
                    if self.sellOrderDict[order.vtOrderID]['timestop'] < self.maxTimeAdd:
                        orderID  = self.sell(self.symbol,self.tick.askPrice1-0.001,order.totalVolume-order.tradedVolume)[0]
                        self.sellOrderDict[orderID] =  {'time':self.tick.datetime,'price':self.tick.askPrice1-0.001,'type':None,'hold':self.timeAdd,
                                                'timestop':self.sellOrderDict[order.vtOrderID]['timestop']+1,'TimeOut':0,
                                                'stopLoss':self.sellOrderDict[order.vtOrderID]['stopLoss'],'total':order.totalVolume-order.tradedVolume}
                    else:
                        ## 多次挂出均未成交的订单按照市价出场
                        self.sell(self.symbol,self.tick.lowerLimit+0.001,order.totalVolume-order.tradedVolume)
                        self.Longcount -= order.totalVolume - order.tradedVolume
                ## 执行完全部操作后删除字典内原有的元素
                del self.sellOrderDict[order.vtOrderID]               
            
            elif order.vtOrderID in self.coverOrderDict:
                if self.coverOrderDict[order.vtOrderID]['type'] == 'stopLoss':
                    self.Shortcount -= order.totalVolume - order.tradedVolume
                    self.cover(self.symbol,self.tick.upperLimit-0.001,order.totalVolume-order.tradedVolume)
                    self.shortWin[0] += 1
                else:
                    ## 对timeout的订单进行处理，按照盘口价格挂单,是否使用对手价值得进一步考虑
                    self.shortWin[1] += self.coverOrderDict[order.vtOrderID]['TimeOut']
                    if self.coverOrderDict[order.vtOrderID]['timestop'] < self.maxTimeAdd:
                        orderID = self.cover(self.symbol,self.tick.bidPrice1+0.001,order.totalVolume-order.tradedVolume)[0]  
                        self.coverOrderDict[orderID] = {'time':self.tick.datetime,'price':self.tick.bidPrice1+0.001,'type':None,'hold':self.timeAdd,
                                                'timestop':self.coverOrderDict[order.vtOrderID]['timestop']+1,'TimeOut':0,
                                                'stopLoss':self.coverOrderDict[order.vtOrderID]['stopLoss'],'total':order.totalVolume-order.tradedVolume}    
                    else:
                        ## 多次挂出未成交的订单按照市价出场
                        self.cover(self.symbol,self.tick.upperLimit-0.001,order.totalVolume-order.tradedVolume)
                        self.Shortcount -= order.totalVolume - order.tradedVolume
                ## 执行完全部操作后删除字典内原有的元素
                del self.coverOrderDict[order.vtOrderID]
            ## 撤销的是开仓单，删除字典并对可开数量进行修改
            elif order.vtOrderID in self.buyOrderDict:
                self.Longcount -= order.totalVolume-order.tradedVolume
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                self.Shortcount -= order.totalVolume - order.tradedVolume
                del self.shortOrderDict[order.vtOrderID]
        
        self.putEvent()


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单  
        self.writeCtaLog(u'Long:%s,short:%s'%(self.longWin,self.shortWin))  
        self.lastTradeTime = datetime.now()      
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

