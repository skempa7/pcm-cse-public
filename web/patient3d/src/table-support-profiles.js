/** Authored support fit from verified MPFB exports; meters, glTF/Babylon coordinates.
 * Source samples and hashes: assets3d/clinical-table/body-support-profiles.json.
 * Table contour is visual support, not a measured clinical finding. */
export const TABLE_SUPPORT_PROFILES=Object.freeze({
  "short-slender": {
    "sourceHash": "26917dbdc9ce30e9a6e4ba4a9376ab5be945ebe9e3ba45cf6e96f0eda90fad3b",
    "heightM": 1.650968064367671,
    "backCushionM": 1.0346928062438965,
    "calfCushionM": 1.0409779968261719,
    "heelCushionM": 1.0780792655944824,
    "calfZ": 0.5,
    "heelZ": 0.730836853981018,
    "pillowZ": -0.75,
    "pillowCenterY": 1.0316956996917725,
    "supportSamples": {
      "occiput": [
        1.0566956996917725,
        0,
        -0.75
      ],
      "back": [
        1.0406928062438965,
        -0.05,
        -0.475
      ],
      "calf": [
        1.0469779968261719,
        -0.15,
        0.5
      ],
      "heel": [
        1.0840792655944824,
        -0.15,
        0.775
      ]
    }
  },
  "standard": {
    "sourceHash": "a39b9f436e212726f200fac5a8bcc7f443a411039ec83f934950bc6f4e83bfcb",
    "heightM": 1.701859975690505,
    "backCushionM": 1.0403252067565918,
    "calfCushionM": 1.0455835285186768,
    "heelCushionM": 1.0849595489501953,
    "calfZ": 0.525,
    "heelZ": 0.7607221460342407,
    "pillowZ": -0.775,
    "pillowCenterY": 1.0379086494445802,
    "supportSamples": {
      "occiput": [
        1.06290864944458,
        0,
        -0.775
      ],
      "back": [
        1.0463252067565918,
        -0.05,
        -0.5
      ],
      "calf": [
        1.0515835285186768,
        -0.15,
        0.525
      ],
      "heel": [
        1.0909595489501953,
        -0.15,
        0.8
      ]
    }
  },
  "tall-full": {
    "sourceHash": "91a97dfd7b7eeee1535721bfb4d94352ca51d91aa7a3f0882434adfe8c47c184",
    "heightM": 1.752623918382822,
    "backCushionM": 1.0453677597045898,
    "calfCushionM": 1.0524888458251953,
    "heelCushionM": 1.0965381088256836,
    "calfZ": 0.55,
    "heelZ": 0.7906407570838928,
    "pillowZ": -0.8,
    "pillowCenterY": 1.0482667446136475,
    "supportSamples": {
      "occiput": [
        1.0732667446136475,
        0,
        -0.8
      ],
      "back": [
        1.0513677597045898,
        -0.05,
        -0.5
      ],
      "calf": [
        1.0584888458251953,
        -0.15,
        0.55
      ],
      "heel": [
        1.1025381088256836,
        0.15,
        0.85
      ]
    }
  }
});
