# encoding: UTF-8

"""
简单配对交易策略模板
"""
# from gevent import monkey

from vnpy.trader.vtConstant import *
# from vnpy.trader.app.ctaStrategy.mail import mail
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
from threading import Thread

from queue import Queue, Empty
import time
import numpy as np
import talib as ta
import math
import datetime
import json
import os

########################################################################


class Strategy_Arbitrage(CtaTemplate):
    """配对交易策略"""
    className = 'This is a magic arbitrage strategy.'
    author = 'leon'
    productType = 'FUTURE'
    # 策略交易标的
    symbolList = []                 # 初始化为空
    activeSymbol = EMPTY_STRING     # 主动品种
    passiveSymbol = EMPTY_STRING    # 被动品种
    asLongpos = EMPTY_STRING        # 主动品种多仓
    asShortpos = EMPTY_STRING       # 主动品种空仓
    psLongpos = EMPTY_STRING        # 被动品种多仓
    psShortpos = EMPTY_STRING       # 被动品种空仓
    posDict = {}                    # 仓位数据缓存
    eveningDict = {}                # 可平仓量数据缓存
    bondDict = {}                   # 保证金数据缓存

    # 策略变量
    posSize = 0
    maxcost = 2  # 设置最大成本为20
    gap_base = 0
    alpha = 0
    miu = 0
    floors = 0
    profits = 0
    base_unit = 0
    floor_volume = 0
    miu_long = 0
    add_profit = 1
    passive_volume = {}
    order_priceMap = {}
    shortTickRate = 0
    longTickRate = 0
    longPriceVol = 0
    shortPriceVol = 0
    orderFlag = False
    levelRate = 20
    stop = False
    in_extend = []
    out_extend = []

    # 用于记录上一个onTrade的结果，回测需要赋予初始状态，这里以全部空仓为初始

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'activeSymbol',
                 'passiveSymbol',
                 'in_extend',
                 'out_extend']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'gap_base',
               'miu', 'floors',
               'profits',
               'base_unit',
               'add_profit',
               'shortTickRate',
               'longTickRate',
               'miu_long',
               'stop'
               ]

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------

    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(Strategy_Arbitrage, self).__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.activeSymbol = self.symbolList[0]  # 流动性好的品种
        self.passiveSymbol = self.symbolList[1]  # 流动性差的品种
        self.catchOrder = Thread(target=self.runCatchOrder)
        self.disposeOrder = Thread(target=self.runDisposeOrder)
        self.catchOrderQueue = Queue()
        self.disposeOrderQueue = Queue()
        self.offset_directionCatchOrderMap = {("开仓", "多"): self.catchShort, (
            "开仓", "空"): self.catchBuy, ("平仓", "多"): self.catchSell, ("平仓", "空"): self.catchCover}
        # 创建K线合成器对象
        # self.bgDict = {
        #     sym: BarGenerator(self.onBar)
        #     for sym in self.symbolList
        # }#用tick生成bar
        # self.hfDict = {sym: BarGenerator(self.onhfBar,xSecond = 10)
        #     for sym in self.symbolList
        # }

        # # 创建数组容器
        # self.amDict = {
        #     sym: ArrayManager()
        #     for sym in self.symbolList
        # }
        self.generateBarDict(self.onBar)
        self.generateHFBar(10)

        # 创建tick数据缓存容器
        self.tickBufferDict = {
            sym: []
            for sym in self.symbolList
        }  # 存下activeSymbol和passiveSymbol的tick
        self.barBufferDict = {
            sym: []
            for sym in self.symbolList
        }  # 存下activeSymbol和passiveSymbol的分钟bar

        self.spreadBuffer = []  # 存下midActivePrice-midPassivePrice
        self.unknowOrderIDMap = {}

        self.midPassiveBuffer = []  # 存下bid1和ask1的中间价
        self.midActiveBuffer = []
        self.current_capital = 500  # 留待之后做动态调仓

        self.active_passiveMap = {}  # 把activeID和passiveID映射到一起
        # self.passive_infoMap={}#以passiveID为key,value分别是miu,gap,flag,pos,volume

        self.long_shortToInt = {"多": -1, "空": 1}  # 把多空跟pos参数映射起来
        self.pos_Map = {-2: -1, 2: 0, -3: 1}  # 在passiveSymbol被拒单时候调用
        self.passive_countList = []
        self.close_openIdMap = {}  # 平仓时的passiveID和开仓时的passiveID映射起来
        self.barSpreadBuffer = []  # bar.close的差值
        self.initbars = 2000
        self.writeCtaLog(u'%s策略初始化' % self.name)
        self.floorDeliverTime = {}
        pastbar = self.loadHistoryBar(self.activeSymbol,
                                      type_="1min",
                                      size=self.initbars)
        pastbar2 = self.loadHistoryBar(
            self.passiveSymbol, type_="1min", size=self.initbars)
        path = os.path.abspath(os.path.dirname(__file__))
        filename = os.path.join(path, "Ye.json")
        with open(filename) as f:
            info = json.load(f)
            info = info[self.activeSymbol]
            self.floors = info["floors"]
            self.profits = info["profits"]
            self.base_unit = info["base_unit"]
            self.in_extend = info["in_extend"]  # 记录维度
            self.out_extend = info["out_extend"]
        self.count = 0
        self.alpha = 0
        # self.floors=[6.2,7.2,8.2,9.2,10.2]
        self.floor_infoMap = {
            floor: {"pos": 0, "isNormal": False, "isEnter": False} for floor in self.floors}

        self.first_floor = list(self.floor_infoMap.keys())[0]
        self.last_floor = list(self.floor_infoMap.keys())[-1]
        # self.profit=[5.2,6.2,7.2,8.2,9.2]
        self.passive_floorMap = {}
        self.floor_tickRate = {floor: out_extend for floor,
                               out_extend in zip(self.floors, self.out_extend)}
        self.floor_priceVol = {floor: in_extend for floor,
                               in_extend in zip(self.floors, self.in_extend)}
        self.floor_volume = {floor: volume for floor,
                             volume in zip(self.floors, self.base_unit)}
        self.open_closeGap = {floor: floor-profit for floor,
                              profit in zip(self.floors, self.profits)}
        self.passiveDateTime = []
        self.activeDateTime = []
        self.floorOpenTimeMap = {}

        for bar, bar2 in zip(pastbar, pastbar2):
            self.barSpreadBuffer.append(bar.close-bar2.close)
            self.barBufferDict[self.passiveSymbol].append(bar2.close)
            self.barBufferDict[self.activeSymbol].append(bar.close)
            self.activeDateTime.append(bar.datetime)
            self.passiveDateTime.append(bar2.datetime)

        self.opentime = pastbar[-1].datetime
        x = np.array(self.barBufferDict[self.passiveSymbol][-240:])
        y = np.array(self.barBufferDict[self.activeSymbol][-240:])

        self.gap_base = 0.001*np.mean(x+y)/2
        # self.alpha=float(np.mean(y)-np.mean(x))
        self.miu = np.mean(self.barSpreadBuffer[-240:])
        self.miu_short = np.mean(self.barSpreadBuffer[-30:])
        self.miu_long = np.mean(self.barSpreadBuffer[-720:])
        miuSpreadMax = max((abs(self.miu_short-self.miu),
                            abs(self.miu_long-self.miu)))
        del self.barBufferDict[self.passiveSymbol][:-240]
        del self.barBufferDict[self.activeSymbol][:-240]
        del self.barSpreadBuffer[:-720]
        del self.activeDateTime[:-240]
        del self.passiveDateTime[:-240]
        self.writeCtaLog("passiveSymbol的bar.close数组的长度%s" %
                         len(self.barBufferDict[self.passiveSymbol]))
        self.writeCtaLog("activeSymbol的bar.close数组的长度%s" %
                         len(self.barBufferDict[self.passiveSymbol]))
        self.writeCtaLog("barSpreadBuffer的长度为:%s" %
                         (len(self.barSpreadBuffer)))
        miuSpreadMax = max((abs(self.miu_short-self.miu),
                            abs(self.miu_long-self.miu)))
        if miuSpreadMax > self.gap_base/2:
            self.gap_base = 1.2*miuSpreadMax
            if miuSpreadMax == (abs(self.miu_long-self.miu)):
                self.writeCtaLog("长期大于短期，所以用miu_long-miu 1.2倍更新gap_base")
            if miuSpreadMax == (abs(self.miu_short-self.miu)):
                self.writeCtaLog("短期大于长期,所以用miu_short-miu 1.2倍更新gap_base")
        else:
            self.gap_base = 1.2*self.gap_base
        self.init15MinClose = self.barBufferDict[self.activeSymbol][-1]
        self.contin15MinCloseReturn = 1
        #用240min的分钟bar预估miu和gap
        self.out = OutEvent(self.activeSymbol, self.passiveSymbol)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        self.out.start()
        self.orderFlag = True
        self.initTime = datetime.datetime.now()
        self.catchOrder.start()
        self.disposeOrder.start()

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def catchBuy(self, order):
        volume = order.tradedVolume-self.passive_volume[order.vtOrderID]
        self.passive_volume[order.vtOrderID] = order.tradedVolume
        self.order_priceMap[order.vtOrderID] = order.price_avg  # 在开仓时保留下价格
        activeID = self.buy(
            self.activeSymbol, self.midActiveBuffer[-1]*1.02, volume, priceType=PRICETYPE_LIMITPRICE)[0]
        passiveID = order.vtOrderID  # 只维护开仓时的passiveID
        self.active_passiveMap[activeID] = passiveID

        self.writeCtaLog(
            "市价追开空"+str(self.tickBufferDict[self.activeSymbol][-1].bidPrice1)+" "+"volume:"+str(volume))

    #---------------------------------------------------------------------
    def catchShort(self, order):
        volume = order.tradedVolume-self.passive_volume[order.vtOrderID]
        self.passive_volume[order.vtOrderID] = order.tradedVolume
        self.order_priceMap[order.vtOrderID] = order.price_avg  # 在开仓时保留下价格
        activeID = self.short(
            self.activeSymbol, self.midActiveBuffer[-1]*0.98, volume, priceType=PRICETYPE_LIMITPRICE)[0]
        passiveID = order.vtOrderID  # 只维护开仓时的passiveID
        self.active_passiveMap[activeID] = passiveID

        self.writeCtaLog(
            "市价追开多"+str(self.tickBufferDict[self.activeSymbol][-1].askPrice1)+" "+"volume:"+str(volume))

    # -----------------------------------------------------------------------------
    def catchSell(self, order):
        # 平仓时映射到开仓时的vtOrderID
        passiveID = self.close_openIdMap[order.vtOrderID]
        volume = order.tradedVolume-self.passive_volume[passiveID]
        self.passive_volume[passiveID] = order.tradedVolume
        activeID = self.sell(
            self.activeSymbol, self.midActiveBuffer[-1]*0.98, volume, priceType=PRICETYPE_LIMITPRICE)[0]
        self.active_passiveMap[activeID] = passiveID
        if order.status == "全部成交":
            del self.close_openIdMap[order.vtOrderID]
        self.writeCtaLog(
            "市价追平多"+str(self.tickBufferDict[self.activeSymbol][-1].askPrice1)+" "+"volume:"+str(volume))

    # -----------------------------------------------------------------------------------
    def catchCover(self, order):
        # 平仓时映射到开仓时的vtOrderID
        passiveID = self.close_openIdMap[order.vtOrderID]
        volume = order.tradedVolume-self.passive_volume[passiveID]
        self.passive_volume[passiveID] = order.tradedVolume
        activeID = self.cover(
            self.activeSymbol, self.midActiveBuffer[-1]*1.02, volume, priceType=PRICETYPE_LIMITPRICE)[0]
        self.active_passiveMap[activeID] = passiveID
        if order.status == "全部成交":
            del self.close_openIdMap[order.vtOrderID]
        self.writeCtaLog(
            "市价追平空"+str(self.tickBufferDict[self.activeSymbol][-1].bidPrice1)+" "+"volume:"+str(volume))

    def runCatchOrder(self):

        while self.orderFlag:
            try:
                order = self.catchOrderQueue.get(
                    block=True, timeout=1)  # 获取事件的阻塞时间设为1秒
                Thread(target=self.onCatchOrder, args=(order,)).start()
            except Empty:
                # self.writeCtaLog("*************")
                pass

    def runDisposeOrder(self):
        while self.orderFlag:
            try:
                order = self.disposeOrderQueue.get(
                    block=True, timeout=1)  # 获取事件的阻塞时间设为1秒
                self.onDisposeOrder(order)
            except Empty:
                # self.writeCtaLog("***********************")
                pass

    def onDisposeOrder(self, order):

        if (order.status == "全部成交" or order.status == "部分成交") and order.vtSymbol == self.activeSymbol and order.vtOrderID not in self.active_passiveMap:
            time.sleep(2)
        if (order.status == "全部成交" or order.status == "部分成交") and order.vtSymbol == self.activeSymbol and order.vtOrderID in self.active_passiveMap:
            passiveID = self.active_passiveMap[order.vtOrderID]
            floor = self.passive_floorMap[passiveID]
            volume = self.passive_volume[passiveID]
            self.floorOpenTimeMap[floor] = order.deliverTime
            self.floorDeliverTime[floor] = order.deliverTime
            if order.offset == "开仓":
                self.writeCtaLog("开仓"+"***"+str(order.vtOrderID)+":"+str(passiveID)+" "+str(
                    self.floor_infoMap[floor]["miu"])+" "+str(self.floor_infoMap[floor]["gap"]))

                self.floor_infoMap[floor]["volume"] = volume

                if order.direction == "多":
                    self.floor_infoMap[floor]["pos"] = -1
                else:
                    self.floor_infoMap[floor]["pos"] = 1
            else:
                #可平仓量减去已经交易的交易量
                self.writeCtaLog("平仓"+"***"+str(order.vtOrderID)+":"+str(passiveID)+" "+str(
                    self.floor_infoMap[floor]["miu"])+" "+str(self.floor_infoMap[floor]["gap"]))
        if order.status == "全部成交":
            if order.vtSymbol == self.activeSymbol and order.offset == "平仓"and order.vtOrderID in self.active_passiveMap and self.active_passiveMap[order.vtOrderID] in self.passive_floorMap:
                passiveID = self.active_passiveMap[order.vtOrderID]
                floor = self.passive_floorMap[passiveID]
                self.floor_infoMap[floor]["volume"] -= order.tradedVolume
                self.writeCtaLog("floor:%s可平仓量为%s" %
                                 (floor, self.floor_infoMap[floor]["volume"]))
                #activeSymbol必定会全部成交，如果没有程序就是异常，目前还没有处理
                if self.floor_infoMap[floor]["volume"] == 0:
                    self.floor_infoMap[floor]["pos"] = 0

                    rev_floor = self.open_closeGap[floor]
                    if self.floor_infoMap[floor]["isAdd"]:
                        self.open_closeGap[floor] = rev_floor+self.add_profit
                    del self.passive_volume[passiveID]
                    del self.passive_floorMap[passiveID]
                    del self.floorOpenTimeMap[floor]

        if order.status == "全部成交" and order.offset == "开仓":
            self.order_priceMap[order.vtOrderID] = order.price_avg
            if order.vtSymbol == self.activeSymbol and order.vtOrderID in self.active_passiveMap and order.vtOrderID in self.order_priceMap:
                passiveID = self.active_passiveMap[order.vtOrderID]
                floor = self.passive_floorMap[passiveID]
                ideal_spread = self.floor_infoMap[floor]["spread"]
                gap_base = self.floor_infoMap[floor]["gap"]
                isAdd = self.floor_infoMap[floor]["isAdd"]
                rev_floor = self.open_closeGap[floor]
                pos = self.floor_infoMap[floor]["pos"]
                if passiveID in self.order_priceMap:
                    if pos == -1 and ideal_spread-(self.order_priceMap[order.vtOrderID]-self.order_priceMap[passiveID]) < -(floor-rev_floor)/4*gap_base and not isAdd:
                        self.open_closeGap[floor] = rev_floor-self.add_profit
                        self.floor_infoMap[floor]["isAdd"] = True
                        self.writeCtaLog("floor:%s 加到了profit" % floor)
                    elif pos == 1 and ideal_spread-(self.order_priceMap[order.vtOrderID]-self.order_priceMap[passiveID]) > (floor-rev_floor)/4*gap_base and not isAdd:
                        self.open_closeGap[floor] = rev_floor-self.add_profit
                        self.floor_infoMap[floor]["isAdd"] = True
                        self.writeCtaLog("floor:%s 加到了profit" % floor)
                    del self.order_priceMap[order.vtOrderID]
                    del self.order_priceMap[passiveID]
            else:
                pass
        if (order.status == "全部成交" or order.status == "部分成交") and order.offset == "开仓" and order.vtSymbol == self.activeSymbol and order.vtOrderID in self.active_passiveMap:
            del self.active_passiveMap[order.vtOrderID]

    def onCatchOrder(self, order):
        if (order.status == "全部成交" or order.status == "部分成交") and order.vtSymbol == self.passiveSymbol and order.vtOrderID in self.passive_countList:
            callback = self.offset_directionCatchOrderMap[(
                order.offset, order.direction)]
            callback(order)
            if order.status == "全部成交" and order.vtSymbol == self.passiveSymbol and order.vtOrderID in self.passive_countList:  # 防止restful怼过去进两遍拒单逻辑
                self.passive_countList.remove(order.vtOrderID)
                self.writeCtaLog(
                    "delete vtOrderID:%s from passive_countList" % (order.vtOrderID))
            # self.active_passiveMap[activeID]=passiveID
        # self.disposeOrderQueue.put(order)
    # ----------------------------------------------------------------------

    def onTick(self, tick):
        """收到行情TICK推送"""
        self.bgDict[tick.vtSymbol].updateTick(tick)
        self.hfDict[tick.vtSymbol].updateHFBar(tick)
        self.out.put(tick)
        self.tickBufferDict[tick.vtSymbol].append(tick)
        if self.stop:
            self.writeCtaLog("自闭两个小时")
            return
       #保证两边都有数据才开始进行后面的交易
        if not self.tickBufferDict[self.activeSymbol]:
            return
        if not self.tickBufferDict[self.passiveSymbol]:
            return

        if len(self.tickBufferDict[self.activeSymbol]) >= 50 and len(self.tickBufferDict[self.passiveSymbol]) >= 50:
            del self.tickBufferDict[self.activeSymbol][:-10]
            del self.tickBufferDict[self.passiveSymbol][:-10]
        #流动性差的品种的bid1和ask1的均值作为计pread的价格
        midPassive = (self.tickBufferDict[self.passiveSymbol][-1].askPrice1 +
                      self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        #流动性好的品种的bid1和ask1的均值作为计算spread的价格
        midActive = (self.tickBufferDict[self.activeSymbol][-1].askPrice1 +
                     self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        #用passive的Buffer存下来midPassive，方便计算均值
        self.midPassiveBuffer.append(midPassive)
        #用active的Buffer存下来midActive，方便计算均值
        self.midActiveBuffer.append(midActive)

        #用spread表示价差，但该价差是假定beta=1的时候算-self.alpha出来的，线性回归的sigma（残差）
        spread = midActive-midPassive-self.alpha

        self.spreadBuffer.append(spread)

        if len(self.spreadBuffer) == 50:
            del self.spreadBuffer[:-10]

        #买价-卖价
        abpassive = self.tickBufferDict[self.passiveSymbol][-1].askPrice1 - \
            self.tickBufferDict[self.passiveSymbol][-1].bidPrice1
        abactive = self.tickBufferDict[self.activeSymbol][-1].askPrice1 - \
            self.tickBufferDict[self.activeSymbol][-1].bidPrice1

        bid_askSpread = self.tickBufferDict[self.activeSymbol][-1].bidPrice1 - \
            self.tickBufferDict[self.activeSymbol][-1].askPrice1
        self.cost = 1/2*(abpassive + abactive) + \
            2*0.0005*(self.tickBufferDict[self.activeSymbol][-1].lastPrice +
                      self.tickBufferDict[self.passiveSymbol][-1].lastPrice)

        if (tick.datetime-self.initTime).total_seconds() <= 60*15:
            return
        self.count += 1
        if self.count == 20:
            #             self.writeCtaLog("本地撤单")
            for passiveID in self.passive_countList:
                self.cancelOrder(passiveID)
        elif self.count == 30:
            self.count = 0
        elif self.count == 10:

            #如果passive的仓位加上正在挂单的passive的仓位要小于限定的最大仓位

                #第一层

            for floor in self.floors:
                pos = self.floor_infoMap[floor]["pos"]
                isNormal = self.floor_infoMap[floor]["isNormal"]
                isEnter = self.floor_infoMap[floor]["isEnter"]

                if bid_askSpread < self.gap_base:
                    if pos == 0 and isEnter:
                        base_unit = self.floor_volume[floor]
                        gap_base = self.gap_base*self.contin15MinCloseReturn
                        if spread > self.miu+1/2*self.gap_base*floor:

                            passiveID = self.buy(
                                self.passiveSymbol, self.tickBufferDict[self.activeSymbol][-1].askPrice1-self.alpha-self.miu-gap_base*floor, base_unit, priceType=PRICETYPE_LIMITPRICE)[0]
                            if passiveID:
                                self.passive_countList.append(passiveID)

                                self.floor_infoMap[floor].update({"passiveID": passiveID, "miu": self.miu, "gap": gap_base, "volume": 0,
                                                                  "pos": 2, "spread": spread, "isAdd": False, "isNormal": False, "should_increase": 0})
                                self.passive_floorMap[passiveID] = floor
                                self.passive_volume[passiveID] = 0
                        elif spread < self.miu-1/2*self.gap_base*floor:

                            #限价单
                            passiveID = self.short(
                                self.passiveSymbol, self.tickBufferDict[self.activeSymbol][-1].bidPrice1-self.alpha-self.miu+gap_base*floor, base_unit, priceType=PRICETYPE_LIMITPRICE)[0]
                            if passiveID:
                                self.passive_countList.append(passiveID)

                                self.floor_infoMap[floor].update({"passiveID": passiveID, "miu": self.miu, "gap": gap_base, "volume": 0,
                                                                  "pos": 2, "spread": spread, "isAdd": False, "isNormal": False, "should_increase": 0})
                                self.passive_floorMap[passiveID] = floor
                                self.passive_volume[passiveID] = 0

                    elif pos == 1 and (tick.datetime-self.opentime).total_seconds() > 10 and isNormal:

                        gap_base = self.floor_infoMap[floor]["gap"]

                        rev_floor = self.open_closeGap[floor] + \
                            self.floor_infoMap[floor]["should_increase"]

                        miu = self.floor_infoMap[floor]["miu"]

                        volume = self.floor_infoMap[floor]["volume"]

                        closeID = self.sell(
                            self.passiveSymbol, self.tickBufferDict[self.activeSymbol][-1].bidPrice1-self.alpha-miu-gap_base*rev_floor, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                        if closeID:
                            passiveID = self.floor_infoMap[floor]["passiveID"]
                            self.close_openIdMap[closeID] = passiveID
                            self.floor_infoMap[floor]["pos"] = -3
                            self.passive_countList.append(closeID)
                            self.passive_volume[passiveID] = 0

                    elif pos == -1 and (tick.datetime-self.opentime).total_seconds() > 10 and isNormal:
                        gap_base = self.floor_infoMap[floor]["gap"]

                        rev_floor = self.open_closeGap[floor] + \
                            self.floor_infoMap[floor]["should_increase"]

                        miu = self.floor_infoMap[floor]["miu"]

                        volume = self.floor_infoMap[floor]["volume"]

                        closeID = self.cover(
                            self.passiveSymbol, self.tickBufferDict[self.activeSymbol][-1].askPrice1-self.alpha-miu+gap_base*rev_floor, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                        if closeID:
                            passiveID = self.floor_infoMap[floor]["passiveID"]
                            self.close_openIdMap[closeID] = passiveID
                            self.floor_infoMap[floor]["pos"] = -2
                            self.passive_countList.append(closeID)
                            self.passive_volume[passiveID] = 0

        self.putEvent()

    # ----------------------------------------------------------------------

    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.amDict[bar.vtSymbol].updateBar(bar)
        self.writeCtaLog("vtSymbol:%s datetime:%s" %
                         (bar.vtSymbol, bar.datetime))

        if bar.datetime > datetime.datetime.now():
            return
        nowaday = datetime.datetime.now()

        if nowaday.weekday()+1 == 5 and (nowaday.hour == 15 or nowaday.hour == 16):
            self.stop = True
        else:
            self.writeCtaLog("today is %d and the hour is %d" %
                             (nowaday.weekday()+1, nowaday.hour))
            self.stop = False

        if bar.vtSymbol == self.activeSymbol:
            if len(self.activeDateTime) == 0:
                self.writeCtaLog("第一次更新bar.datetime")
                self.barBufferDict[self.activeSymbol].append(bar.close)
                self.activeDateTime.append(bar.datetime)
                self.writeCtaLog("activeSymbol的bar.close数组的长度%s" %
                                 len(self.barBufferDict[self.activeSymbol]))
                if len(self.passiveDateTime) == 0:
                    return
                elif (bar.datetime-self.passiveDateTime[-1]).total_seconds() <= 5:
                    if len(self.barBufferDict[self.passiveSymbol]) == 0:
                        return
                    self.barSpreadBuffer.append(
                        bar.close-self.barBufferDict[self.passiveSymbol][-1]-self.alpha)
                    self.writeCtaLog("passiveSymbol先到更新价差")
                    self.writeCtaLog("barSpreadBuffer的长度为:%s" %
                                     (len(self.barSpreadBuffer)))
            elif (bar.datetime-self.activeDateTime[-1]).total_seconds() >= 55:
                self.activeDateTime.append(bar.datetime)
                self.barBufferDict[self.activeSymbol].append(bar.close)
                self.writeCtaLog("activeSymbol的bar.close数组的长度%s" %
                                 len(self.barBufferDict[self.activeSymbol]))
                if len(self.passiveDateTime) == 0:
                    return
                elif (bar.datetime-self.passiveDateTime[-1]).total_seconds() <= 5:
                    if len(self.barBufferDict[self.passiveSymbol]) == 0:
                        return
                    self.barSpreadBuffer.append(
                        bar.close-self.barBufferDict[self.passiveSymbol][-1]-self.alpha)
                    self.writeCtaLog("passiveSymbol先到更新价差")
                    self.writeCtaLog("barSpreadBuffer的长度为:%s" %
                                     (len(self.barSpreadBuffer)))
        if bar.vtSymbol == self.passiveSymbol:
            if len(self.passiveDateTime) == 0:
                self.passiveDateTime.append(bar.datetime)
                self.barBufferDict[self.passiveSymbol].append(bar.close)
                self.writeCtaLog("passiveSymbol的bar.close数组的长度%s" %
                                 len(self.barBufferDict[self.passiveSymbol]))
                self.writeCtaLog("第一次更新bar.datetime")
                if len(self.activeDateTime) == 0:
                    return
                elif (bar.datetime-self.activeDateTime[-1]).total_seconds() <= 5:
                    if len(self.barBufferDict[self.activeSymbol]) == 0:
                        return
                    self.barSpreadBuffer.append(
                        self.barBufferDict[self.activeSymbol][-1]-bar.close-self.alpha)
                    self.writeCtaLog("activeSymbol先到更新价差")
                    self.writeCtaLog("barSpreadBuffer的长度为:%s" %
                                     (len(self.barSpreadBuffer)))
            elif (bar.datetime-self.passiveDateTime[-1]).total_seconds() >= 55:
                self.passiveDateTime.append(bar.datetime)
                self.barBufferDict[self.passiveSymbol].append(bar.close)
                self.writeCtaLog("passiveSymbol的bar.close数组的长度%s" %
                                 len(self.barBufferDict[self.passiveSymbol]))
                if len(self.activeDateTime) == 0:
                    return
                elif (bar.datetime-self.activeDateTime[-1]).total_seconds() <= 5:
                    if len(self.barBufferDict[self.activeSymbol]) == 0:
                        return
                    self.barSpreadBuffer.append(
                        self.barBufferDict[self.activeSymbol][-1]-bar.close-self.alpha)
                    self.writeCtaLog("activeSymbol先到更新价差")
                    self.writeCtaLog("barSpreadBuffer的长度为:%s" %
                                     (len(self.barSpreadBuffer)))
            #观察到有1min同一品种推多个bar的，所以在这里进行处理
                for floor in list(self.floorOpenTimeMap.keys()):
                    if (bar.datetime-self.floorOpenTimeMap[floor]).total_seconds() >= 115:
                        self.floor_infoMap[floor]["should_increase"] += (
                            floor-self.open_closeGap[floor])/10
                        self.floorOpenTimeMap[floor] = bar.datetime
                        rev_floor = self.open_closeGap[floor]
                        gap_base = self.floor_infoMap[floor]["gap"]
                        self.writeCtaLog("一分钟到,此时floor:%s价差已增加:%s" % (
                            floor, self.floor_infoMap[floor]["should_increase"]))
                        if (floor-rev_floor-self.floor_infoMap[floor]["should_increase"]) <= 2*gap_base:
                            pos = self.floor_infoMap[floor]["pos"]
                            miu = self.floor_infoMap[floor]["miu"]
                            gap = self.gap_base*floor
                            volume = self.floor_infoMap[floor]["volume"]
                            if pos == -1:
                                closeID = self.cover(
                                    self.passiveSymbol, self.midPassiveBuffer[-1]*1.02, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                                self.close_openIdMap[closeID] = self.floor_infoMap[floor]["passiveID"]
                                self.floor_infoMap[floor]["pos"] = -2
                                self.passive_volume[self.floor_infoMap[floor]
                                                    ["passiveID"]] = 0
                                self.passive_countList.append(closeID)
                            elif pos == 1:
                                closeID = self.sell(
                                    self.passiveSymbol, self.midPassiveBuffer[-1]*0.98, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                                self.passive_volume[self.floor_infoMap[floor]
                                                    ["passiveID"]] = 0
                                self.close_openIdMap[closeID] = self.floor_infoMap[floor]["passiveID"]
                                self.passive_countList.append(closeID)
                                self.floor_infoMap[floor]["pos"] = -3
                            self.writeCtaLog(
                                "移动止损过程中，发现profit不能cover手续费，故直接止损")

                for order in list(self.unknowOrderIDMap.values()):
                    if order.vtSymbol == self.passiveSymbol and (bar.datetime-order.deliverTime).total_seconds() > 120:
                        if order.offset == "平仓" and order.vtOrderID in self.close_openIdMap:  # 平仓订单撤销把pos和flag修改，让它恢复原样
                            pos = self.long_shortToInt[order.direction]
                            passiveID = self.close_openIdMap[order.vtOrderID]
                            floor = self.passive_floorMap[passiveID]
                            self.floor_infoMap[floor]["pos"] = pos
                            self.writeCtaLog("进入未知passiveSymbol平仓")
                            del self.passive_volume[passiveID]
                            del self.close_openIdMap[order.vtOrderID]
                        # 如果开仓的时候订单就没了，就直接把字典删除，让它恢复没有下单一样
                        elif order.offset == "开仓" and self.floor_infoMap[self.passive_floorMap[order.vtOrderID]]["volume"] == 0 and order.vtOrderID in self.passive_countList:
                            self.floor_infoMap[self.passive_floorMap[order.vtOrderID]]["pos"] = 0
                            # 不管开仓还是平仓订单的count单独维护，在收到未成交的委托的时候被初始化为0
                            self.passive_countList.remove(order.vtOrderID)
                            self.writeCtaLog("进入未知passiveSymbol开仓")
                            del self.passive_volume[order.vtOrderID]
                        del self.unknowOrderIDMap[order.vtOrderID]
                    elif order.vtSymbol == self.activeSymbol and (bar.datetime-order.deliverTime).total_seconds() > 60:
                        volume = order.totalVolume
                        passiveID = self.active_passiveMap[order.vtOrderID]
                        del self.active_passiveMap[order.vtOrderID]
                        if order.direction == "多" and order.offset == "开仓":
                            #                     print("市价追开空")
                            activeID = self.buy(
                                self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                            self.writeCtaLog(
                                "市价追开多"+str(self.midActiveBuffer[-1])+" "+"volume:"+str(volume))

                        elif order.direction == "空" and order.offset == "开仓":
                            #                     print("市价追开多")
                            activeID = self.short(
                                self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                            self.writeCtaLog(
                                "市价追开多"+str(self.midActiveBuffer[-1])+" "+"volume:"+str(volume))

                        elif order.direction == "多" and order.offset == "平仓":
                            #                     print("市价追平多")
                            activeID = self.cover(
                                self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                            self.writeCtaLog(
                                "市价追平多"+str(self.midActiveBuffer[-1])+" "+"volume:"+str(volume))

                        elif order.direction == "空" and order.offset == "平仓":
                            #                     print("市价追平空")
                            activeID = self.sell(
                                self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]
                            self.writeCtaLog(
                                "市价追平空"+str(self.midActiveBuffer[-1])+" "+"volume:"+str(volume))

                        if activeID:
                            self.active_passiveMap[activeID] = passiveID
                        self.writeCtaLog(u'未知重新发市价单：%s,%s,%s,%s' % (
                            order.vtSymbol, order.direction, order.offset, order.totalVolume))
                        del self.unknowOrderIDMap[order.vtOrderID]

                for floor in self.floors:
                    pos = self.floor_infoMap[floor]["pos"]
                    if pos == -1:
                        miu = self.floor_infoMap[floor]["miu"]
                        gap = self.gap_base*floor
                        volume = self.floor_infoMap[floor]["volume"]

                        if (self.spreadBuffer[-1] < miu-4*gap or self.miu < miu-gap):
                            closeID = self.cover(
                                self.passiveSymbol, self.midPassiveBuffer[-1]*1.02, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                            self.close_openIdMap[closeID] = self.floor_infoMap[floor]["passiveID"]
                            self.floor_infoMap[floor]["pos"] = -2
                            self.passive_volume[self.floor_infoMap[floor]
                                                ["passiveID"]] = 0
                            self.passive_countList.append(closeID)
                            if self.spreadBuffer[-1] < miu-4*gap:
                                self.writeCtaLog("向下偏离价差强平")
                            else:
                                self.writeCtaLog("miu向下突破miu-gap")
                    elif pos == 1:
                        miu = self.floor_infoMap[floor]["miu"]
                        gap = self.gap_base*floor
                        volume = self.floor_infoMap[floor]["volume"]

                        if (self.spreadBuffer[-1] > miu+4*gap or self.miu > miu+gap):
                            closeID = self.sell(
                                self.passiveSymbol, self.midPassiveBuffer[-1]*0.98, volume, priceType=PRICETYPE_LIMITPRICE)[0]
                            self.passive_volume[self.floor_infoMap[floor]
                                                ["passiveID"]] = 0
                            self.close_openIdMap[closeID] = self.floor_infoMap[floor]["passiveID"]
                            self.passive_countList.append(closeID)
                            self.floor_infoMap[floor]["pos"] = -3
                            if self.spreadBuffer[-1] > miu+4*gap:
                                self.writeCtaLog("向上偏离价差强平")
                            else:
                                self.writeCtaLog("miu向上突破miu+gap")
        if len(self.barSpreadBuffer) % 15 == 0:
            x = np.array(self.barBufferDict[self.passiveSymbol][-240:])
            y = np.array(self.barBufferDict[self.activeSymbol][-240:])
            gap_base = 0.001*np.mean(x+y)/2
            # self.alpha=float(np.mean(y)-np.mean(x))
            self.miu = np.mean(self.barSpreadBuffer[-240:])
            self.miu_long = np.mean(self.barSpreadBuffer[-720:])
            self.miu_short = np.mean(self.barSpreadBuffer[-30:])
            miuSpreadMax = max(
                (abs(self.miu_short-self.miu), abs(self.miu_long-self.miu)))
            if miuSpreadMax > gap_base/2:
                gap_base = 1.2*miuSpreadMax
                if miuSpreadMax == (abs(self.miu_long-self.miu)):
                    self.writeCtaLog("长期大于短期，所以用miu_long-miu 1.2倍更新gap_base")
                if miuSpreadMax == (abs(self.miu_short-self.miu)):
                    self.writeCtaLog("短期大于长期,所以用miu_short-miu 1.2倍更新gap_base")
            else:
                gap_base = 1.2*self.gap_base
            # if self.gap_base - gap_base > gap_base:
            #     self.writeCtaLog("本次的gap_base小于上次的gap_base太多，故再次更新")
            #     gap_base =  (self.gap_base + gap_base)/2
            self.gap_base = gap_base
            # self.out.miu(self.miu)

            self.init15MinClose = self.barBufferDict[self.activeSymbol][-1]
            # self.out.gap(self.gap_base)
            self.writeCtaLog("十五分钟，时间到改变miu:%s和gap:%s" %
                             (self.miu, self.gap_base))
        if len(self.barSpreadBuffer) % 15 == 0:
            del self.barBufferDict[self.passiveSymbol][:-240]
            del self.barBufferDict[self.activeSymbol][:-240]
            del self.activeDateTime[:-240]
            del self.passiveDateTime[:-240]
            del self.barSpreadBuffer[:-720]
            self.writeCtaLog("价差数量到了15，删除一部分")

    def onHFBar(self, bar):
        if bar.vtSymbol == self.activeSymbol:
            self.longTickRate = self.out.longTickRate
            self.shortTickRate = self.out.shortTickRate
            self.longPriceVol = self.out.longPriceVol
            self.shortPriceVol = self.out.shortPriceVol
            self.contin15MinCloseReturn = max(
                1, abs((bar.close-self.init15MinClose)/self.init15MinClose)*2.5+0.9)
            self.writeCtaLog("this 10s return is %s" % abs(
                (bar.close-self.init15MinClose)/self.init15MinClose))
            if self.contin15MinCloseReturn > 1:
                self.writeCtaLog("波幅较大，动态更新gap_base")

            if bar.vtSymbol == self.activeSymbol:
                self.writeCtaLog(bar.vtSymbol+":" +
                                 "longTimeRate=%s" % self.longTickRate)
                self.writeCtaLog(bar.vtSymbol+":" +
                                 "shortTimeRate=%s" % self.shortTickRate)
                self.writeCtaLog(bar.vtSymbol+":" +
                                 "longPriceVol=%s" % self.longPriceVol)
                self.writeCtaLog(bar.vtSymbol+":" +
                                 "shortPriceVol=%s" % self.shortPriceVol)
                for floor in self.floors:
                    out_percentage = self.floor_tickRate[floor]
                    in_percentage = self.floor_priceVol[floor]
                    if self.shortTickRate >= out_percentage*self.longTickRate:
                        self.floor_infoMap[floor]["isNormal"] = False
                        self.writeCtaLog(
                            str(floor)+"isNormal has been setted to False")
                    else:
                        self.floor_infoMap[floor]["isNormal"] = True
                    if self.shortPriceVol >= in_percentage*1.2*self.longPriceVol or self.spreadBuffer[-1] > self.miu+self.gap_base*self.last_floor*1.2 or self.spreadBuffer[-1] < self.miu-self.gap_base*self.last_floor*1.2:
                        self.floor_infoMap[floor]["isEnter"] = False
                        self.writeCtaLog(
                            str(floor)+"isEnter has been setted to False")
                    else:
                        self.floor_infoMap[floor]["isEnter"] = True
                    if floor in self.floorDeliverTime:
                        if (bar.datetime - self.floorDeliverTime[floor]).total_seconds() <= 900:
                            self.floor_infoMap[floor]["isEnter"] = False
                        else:
                            del self.floorDeliverTime[floor]

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        if (order.status == "全部成交" or order.status == "部分成交"):
            self.catchOrderQueue.put(order)
            self.disposeOrderQueue.put(order)
        if order.status == "已撤销":  # 只有passive会撤销所以不判断symbol默认passiveSymbol
            if order.offset == "平仓" and order.tradedVolume == 0 and order.vtOrderID in self.close_openIdMap:  # 平仓订单撤销把pos和flag修改，让它恢复原样
                pos = self.long_shortToInt[order.direction]
                passiveID = self.close_openIdMap[order.vtOrderID]
                floor = self.passive_floorMap[passiveID]
                self.floor_infoMap[floor]["pos"] = pos
                del self.close_openIdMap[order.vtOrderID]
            elif order.offset == "平仓" and order.tradedVolume > 0 and order.vtOrderID in self.close_openIdMap:
                pos = self.long_shortToInt[order.direction]
                passiveID = self.close_openIdMap[order.vtOrderID]
                floor = self.passive_floorMap[passiveID]
                self.floor_infoMap[floor]["pos"] = pos
            elif order.offset == "开仓" and order.vtSymbol == self.passiveSymbol and order.tradedVolume > 0:
                self.order_priceMap[order.vtOrderID] = order.price_avg
            elif order.offset == "开仓" and order.tradedVolume == 0 and order.vtOrderID in self.passive_countList:  # 如果开仓的时候订单就没了，就直接把字典删除，让它恢复没有下单一样
                self.floor_infoMap[self.passive_floorMap[order.vtOrderID]]["pos"] = 0
                # 不管开仓还是平仓订单的count单独维护，在收到未成交的委托的时候被初始化为0
                self.passive_countList.remove(order.vtOrderID)

        ###############################____________________
        #判断是否因为滑点增大出场,然后是否要减少出场难度,记录开仓时间

        if order.status == "拒单":
            if order.vtSymbol == self.passiveSymbol:
                if order.vtOrderID in self.close_openIdMap:
                    passiveID = self.close_openIdMap[order.vtOrderID]
                    del self.close_openIdMap[order.vtOrderID]
                else:
                    passiveID = order.vtOrderID
                    del self.passive_volume[passiveID]
                floor = self.passive_floorMap[passiveID]
                pos = self.pos_Map[self.floor_infoMap[floor]["pos"]]
                self.floor_infoMap[floor]["pos"] = pos

            elif order.vtSymbol == self.activeSymbol:
                if '20018' in order.rejectedInfo:
                    volume = order.totalVolume
                    passiveID = self.active_passiveMap[order.vtOrderID]
                    del self.active_passiveMap[order.vtOrderID]
                    if order.direction == "多" and order.offset == "开仓":
                        #                     print("市价追开空")
                        activeID = self.buy(
                            self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                        self.writeCtaLog(
                            "市价追开多"+str(self.tickBufferDict[self.activeSymbol][-1].askPrice1)+" "+"volume:"+str(volume))

                    elif order.direction == "空" and order.offset == "开仓":
                        #                     print("市价追开多")
                        activeID = self.short(
                            self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                        self.writeCtaLog(
                            "市价追开多"+str(self.tickBufferDict[self.activeSymbol][-1].bidPrice1)+" "+"volume:"+str(volume))

                    elif order.direction == "多" and order.offset == "平仓":
                        #                     print("市价追平多")
                        activeID = self.cover(
                            self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]

                        self.writeCtaLog(
                            "市价追平多"+str(self.tickBufferDict[self.activeSymbol][-1].askPrice1)+" "+"volume:"+str(volume))

                    elif order.direction == "空" and order.offset == "平仓":
                        #                     print("市价追平空")
                        activeID = self.sell(
                            self.activeSymbol, order.price, volume, priceType=PRICETYPE_MARKETPRICE)[0]
                        self.writeCtaLog(
                            "市价追平空"+str(self.tickBufferDict[self.activeSymbol][-1].bidPrice1)+" "+"volume:"+str(volume))

                    if activeID:
                        self.active_passiveMap[activeID] = passiveID
                    self.writeCtaLog(u'拒单重新发市价单：%s,%s,%s,%s' % (
                        order.vtSymbol, order.direction, order.offset, order.totalVolume))
                if "20007" in order.rejectedInfo:
                    #如果再发一遍忽略
                    self.writeCtaLog("volume为0被拒单")

        if order.status == "未知":
            self.unknowOrderIDMap[order.vtOrderID] = order

        # if order.status!="未成交" and order.status!="已撤销":
        #     content = u'stg_onorder收到的订单状态, statu:%s, id:%s, vtSymbol:%s'%(order.status, order.vtOrderID, order.vtSymbol)
        #     self.mail(content)   # 邮件模块可以将信息发送给策略师，第一个参数为收件人邮件地址，第二个参数为邮件正文

        self.writeCtaLog("order.status %s order.vtSymbol %s order.vtOrderID %s order.direction %s order.offset %s order.price:%s cost:%s spread:%s " % (
            order.status, order.vtSymbol, order.vtOrderID, order.offset, order.direction, order.price, self.cost, self.spreadBuffer[-1]))

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # self.writeCtaLog(u'%s,%s成交了,方向：%s,  开平：%s'%(trade.orderID, trade.vtSymbol, trade.direction, trade.offset)

        if trade.offset == "开仓":
            self.opentime = datetime.datetime.now()

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass


class OutEvent(object):
    #----------------------------------------------------------------------
    def __init__(self, activeSymbol, passiveSymbol):
        """初始化事件引擎"""
        # 事件队列
        self.__queue = Queue()

        self.activeSymbol = activeSymbol
        self.passiveSymbol = passiveSymbol

        self.tickBufferDict = {symbol: []
                               for symbol in [activeSymbol, passiveSymbol]}
        # 事件引擎开关
        self.__active = False
        self.shortTimeCountBufferDict = {symbol: []
                                         for symbol in [activeSymbol, passiveSymbol]}
        self.longTimeCountBufferDict = {symbol: []
                                        for symbol in [activeSymbol, passiveSymbol]}
        # 事件处理线程
        self.__thread = Thread(target=self.__run)
        self.__shortTickRate = 0
        self.__longTickRate = 0
        self.__longPriceVol = 0
        self.__shortPriceVol = 0
        self.__longTerm = 300
        self.__shortTerm = 10
        self.isNormalTickRate = True
        self.isNormalPriceVol = True

    #----------------------------------------------------------------------

    def __run(self):
        """引擎运行"""
        while self.__active == True:
            try:
                tick = self.__queue.get(block=True, timeout=1)  # 获取事件的阻塞时间设为1秒
                self.__process(tick)
            except Empty:
                # print("没有tick过来")
                pass

    #----------------------------------------------------------------------
    def __process(self, tick):
        """处理tick"""
        if tick.vtSymbol == self.activeSymbol:
            if len(self.tickBufferDict[tick.vtSymbol]) == 0:
                self.tickBufferDict[tick.vtSymbol].append(tick)
                self.shortTimeCountBufferDict[tick.vtSymbol].append(tick)
                self.longTimeCountBufferDict[tick.vtSymbol].append(tick)
                print("第一次tick进入")
            #保证lastPrice价格是不同的，此时tick才存进list里
            else:
                firstShortTick = self.shortTimeCountBufferDict[tick.vtSymbol][0]

                # print("tick.datetime:"+str(tick.datetime))
                if (tick.datetime-firstShortTick.datetime).total_seconds() > self.__shortTerm:
                    self.__shortTickRate = len(
                        self.shortTimeCountBufferDict[tick.vtSymbol])/self.__shortTerm
                    shortLastPriceArray = np.array(
                        list(map(lambda x: x.lastPrice, self.shortTimeCountBufferDict[tick.vtSymbol])))

                    self.__shortPriceVol = np.std(
                        (shortLastPriceArray[1:]-shortLastPriceArray[:-1])/shortLastPriceArray[:-1])
                    self.shortTimeCountBufferDict[tick.vtSymbol] = []
                    print("成功更新短期tick速率和price波动率")
                    longLastPriceArray = np.array(
                        list(map(lambda x: x.lastPrice, self.longTimeCountBufferDict[tick.vtSymbol])))
                    self.__longTickRate = len(
                        self.longTimeCountBufferDict[tick.vtSymbol])/self.__longTerm
                    self.__longPriceVol = np.std(
                        (longLastPriceArray[1:]-longLastPriceArray[:-1])/longLastPriceArray[:-1])
                    print("成功更新长期tick速率和price波动率")

                while (tick.datetime-self.longTimeCountBufferDict[tick.vtSymbol][0].datetime).total_seconds() > self.__longTerm:
                    self.longTimeCountBufferDict[tick.vtSymbol].pop(0)
            if tick.datetime > self.tickBufferDict[tick.vtSymbol][-1].datetime:
                self.shortTimeCountBufferDict[tick.vtSymbol].append(tick)
                self.tickBufferDict[tick.vtSymbol].append(tick)
                self.longTimeCountBufferDict[tick.vtSymbol].append(tick)
            else:
                if len(self.shortTimeCountBufferDict[tick.vtSymbol]) == 0:
                    self.shortTimeCountBufferDict[tick.vtSymbol].append(tick)
                    self.longTimeCountBufferDict[tick.vtSymbol].append(tick)
                else:
                    self.shortTimeCountBufferDict[tick.vtSymbol].insert(
                        -2, tick)
                    self.longTimeCountBufferDict[tick.vtSymbol].insert(
                        -2, tick)
                self.tickBufferDict[tick.vtSymbol].insert(-2, tick)

        if len(self.tickBufferDict[self.activeSymbol]) >= 50:
            del self.tickBufferDict[self.activeSymbol][:-10]

    #----------------------------------------------------------------------
    def start(self):
        """
        引擎启动
        """
        # 将引擎设为启动
        self.__active = True
        # 启动事件处理线程
        self.__thread.start()

    #----------------------------------------------------------------------

    def stop(self):
        """停止引擎"""
        # 将引擎设为停止
        self.__active = False

        # 等待事件处理线程退出
        self.__thread.join()

    #----------------------------------------------------------------------
    def put(self, tick):
        """向tick中存入队列"""
        self.__queue.put(tick)

    @property
    def longTickRate(self):
        return self.__longTickRate

    @property
    def shortTickRate(self):
        return self.__shortTickRate

    @property
    def longPriceVol(self):
        return self.__longPriceVol

    @property
    def shortPriceVol(self):
        return self.__shortPriceVol
