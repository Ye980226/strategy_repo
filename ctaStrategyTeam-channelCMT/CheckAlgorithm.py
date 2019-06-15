
def on60MinBar(self, bar):
    am = self.getArrayManager(bar.vtSymbol, "60m")
    print(am.ts_rank(am.close, 20, array=True))
    print(am.cov(am.close, am.volume, 20, array=True))
    print('ts_kurt', am.ts_kurt(am.close,  20, array=True))
    print('ts_skew', am.ts_skew(am.close, 20, array=True))
    print('calReturn', am.calReturn(am.close, 1))