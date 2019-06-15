




# 前一根是阳线或阴线，后一根吞噬
def engulfingCandle(self, openArray, highArray, lowArray, closeArray, minBarPct=1.01):
    candleStatus = 0
    lastPositive = closeArray[-2]>minBarPct*openArray[-2]
    lastNegative = openArray[-2]>minBarPct*closeArray[-2]

    if lastPositive:
        if openArray[-1]>=openArray[-2] and closeArray[-1]<lowArray[-2]:
            candleStatus = -1
    elif lastNegative:
        if openArray[-1] <= openArray[-2] and closeArray[-1] > highArray[-2]:
            candleStatus = 1
    return candleStatus

