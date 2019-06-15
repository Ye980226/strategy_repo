from stepwiseOptClass import stepwiseOpt
import numpy as np
import json
import os
from outsideCandleStrategyV2 import outsideCandleStrategy

STRATEGYCLASS = outsideCandleStrategy

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180601 00:00:00",
                "endDate": "20190516 23:59:00",
                "slippage": 0.5,
                "rate": 0.002,
                'setDB_URI': "mongodb://192.168.4.132:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["btc.usd.q:okef"]
                }


# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [        
            # {"pick_freq_param": 
            #     {
            #     "volumeMultiple": np.arange(0.1,0.9,0.1),
            #     "range_": np.arange(0.001,0.005,0.0005)
                
            #     }
            # }, 
            {"pick_best_param": 
                {
                "rocPeriod": range(5,50,5)
                }
            }
            # {"pick_freq_param": 
            #     {
            #     "rsiUpThreshold": range(50,90,5),
            #     "rsiDnThreshold": range(10,45,5)
                
            #     }
            # }
]

multiSymbolList = [
                    # ['btc.usd.q:okef'],
#                     ['eos.usd.q:okef'],
#                     ['eth.usd.q:okef'],
#                     ['ltc.usd.q:okef']
                  ]


def main():
    path = os.path.split(os.path.realpath(__file__))[0]
    with open(path+"//CTA_setting.json") as f:
        globalSetting = json.load(f)[0]

    # for s in multiSymbolList:
    #     ENGINESETTING["symbolList"] = s
    globalSetting.update(ENGINESETTING)
    optimizer = stepwiseOpt(STRATEGYCLASS, ENGINESETTING, OPT_TARGET, OPT_TASK, globalSetting, '../optResult')
    optimizer.runMemoryParallel()

if __name__ == '__main__':
    main()