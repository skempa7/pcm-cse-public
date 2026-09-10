/** Authored support fit from verified MPFB exports; meters, glTF/Babylon coordinates.
 * Source samples and hashes: assets3d/clinical-table/body-support-profiles.json.
 * Table contour is visual support, not a measured clinical finding. */
export const TABLE_SUPPORT_PROFILES=Object.freeze({
  "short-slender": {
    "sourceHash": "64451a2cf01579774f5cd6862d289281658e7c5d6f7c1f895873686a5b7d99d9",
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
    "sourceHash": "c59ab1013efd64f0885ace851f3b3fbcbe7d2b9c6a880ac134d43c78023e50be",
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
    "sourceHash": "fdf3dc4d9af83d9c9027ffde49fdb99e9d037f99c9258bb894f4773377253e07",
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
    "sourceHash": "b89a6f1f444aebad3c02608e9c4059b54eebdbae03bbedd777fee4b9b48f0d60",
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
