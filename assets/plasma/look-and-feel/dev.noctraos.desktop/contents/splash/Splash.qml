/*
    NoctraOS splash (flavour kubuntu): the NoctraOS lockup on the desktop canvas and a thin amber bar that fills as Plasma
    starts. Shown by ksplashqml after login (ksplashrc: Engine=KSplashQML, Theme=dev.noctraos.desktop). Artwork:
    scripts/render-kubuntu-branding.py. Structure follows Breeze's splash (org.kde.breeze.desktop).

    SPDX-License-Identifier: MIT
*/

import QtQuick

Rectangle {
    id: root
    color: "#121212"

    // ksplash raises this as the session starts: 1 at the beginning, 6 when the desktop is ready.
    property int stage

    onStageChanged: {
        if (stage == 2) {
            introAnimation.running = true;
        }
    }

    Item {
        id: content
        anchors.fill: parent
        opacity: 0

        Image {
            id: lockup
            anchors.centerIn: parent
            source: "images/lockup.png"
            // The picture is drawn at twice this height, so it stays sharp on HiDPI screens.
            height: Math.round(Math.min(root.height / 14, 96))
            sourceSize.height: height * 2
            fillMode: Image.PreserveAspectFit
            smooth: true
            asynchronous: true
        }

        Rectangle {
            id: track
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: lockup.bottom
            anchors.topMargin: Math.round(lockup.height * 0.8)
            width: Math.round(lockup.height * 2.8)
            height: 3
            color: "#333333"

            Rectangle {
                anchors.left: parent.left
                height: parent.height
                color: "#e68e0d"
                width: Math.round(parent.width * Math.min(Math.max(root.stage, 1), 6) / 6)
                Behavior on width {
                    NumberAnimation { duration: 400; easing.type: Easing.OutCubic }
                }
            }
        }
    }

    OpacityAnimator {
        id: introAnimation
        running: false
        target: content
        from: 0
        to: 1
        duration: 600
        easing.type: Easing.InOutQuad
    }
}
