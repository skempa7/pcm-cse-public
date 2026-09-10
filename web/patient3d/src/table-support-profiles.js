/** Authored support fit from verified MPFB exports; meters, glTF/Babylon coordinates.
 * Source samples and hashes: assets3d/clinical-table/body-support-profiles.json.
 * Table contour is visual support, not a measured clinical finding. */
export const TABLE_SUPPORT_PROFILES=Object.freeze({
  "short-slender": {
    "sourceHash": "73281741461f052ed5f2afbfc10de5338a134a36199ddeb63ae6e799289c79d0",
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
    "sourceHash": "00172e5faed557dc7e77356c03b0800ffd1fd49617f1685dc92fdab06a4cdd72",
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
    "sourceHash": "04fa4c4df8023f475b00bef32242e00181becb6228f6a6324767e384cc7b2602",
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
  },
  "male": {
    "sourceHash": "0fe26a2ea00d406dbf5056f0d84fc12540b30bde4df9fcd5cdce5c4486974bce",
    "heightM": 1.78,
    "backCushionM": 1.0205955924987793,
    "calfCushionM": 1.0182466926574707,
    "heelCushionM": 1.0479929866790771,
    "calfZ": 0.525,
    "heelZ": 0.8250788903236389,
    "pillowZ": -0.8,
    "pillowCenterY": 1.0411747455596925,
    "supportSamples": {
      "occiput": [
        1.0661747455596924,
        0,
        -0.8
      ],
      "back": [
        1.0265955924987793,
        -0.1,
        -0.45
      ],
      "calf": [
        1.0242466926574707,
        -0.15,
        0.525
      ],
      "heel": [
        1.0539929866790771,
        -0.15,
        0.875
      ]
    }
  }
});
