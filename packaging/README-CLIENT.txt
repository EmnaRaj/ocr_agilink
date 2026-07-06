========================================================================
  AGILINK — Fiches Suiveuses  ·  Version de test (locale)
========================================================================

Cette application fonctionne ENTIÈREMENT sur votre ordinateur. Aucune
donnée n'est envoyée sur un serveur : les fiches scannées, la base de
données et le stockage restent chez vous. (Seule la lecture de l'écriture
manuscrite par l'IA passe par le service OpenRouter — voir l'étape 2.)

------------------------------------------------------------------------
  CE QU'IL VOUS FAUT
------------------------------------------------------------------------
  • Docker Desktop (gratuit) :
        https://www.docker.com/products/docker-desktop
    Installez-le, lancez-le, et attendez qu'il indique "Running".
  • Une clé API OpenRouter (gratuite à créer) :
        https://openrouter.ai/keys

------------------------------------------------------------------------
  DÉMARRER — 3 ÉTAPES
------------------------------------------------------------------------
  1. Décompressez ce dossier où vous voulez.

  2. Ouvrez le fichier « .env » avec le Bloc-notes (Windows) ou TextEdit
     (Mac). Trouvez les 2 lignes contenant :
            PASTE-YOUR-OPENROUTER-KEY-HERE
     Remplacez ce texte par votre clé OpenRouter (elle commence par
     « sk-or-... »). Enregistrez le fichier.

  3. Lancez l'application :
        • Windows : double-cliquez sur  start-windows.bat
        • Mac     : double-cliquez sur  start-mac.command
        • Linux   : exécutez  ./start-linux.sh

     Le premier démarrage prend quelques minutes (téléchargement +
     construction). Ensuite, l'application s'ouvre automatiquement dans
     votre navigateur à l'adresse :

            http://localhost:3000

------------------------------------------------------------------------
  UTILISATION
------------------------------------------------------------------------
  • « Scanner une fiche » : importez un ou plusieurs PDF/photos de fiches
    suiveuses. L'IA lit le tableau et remplit chaque champ.
  • « Suivi des scans »   : suivez l'avancement de chaque fichier.
  • « Historique »        : consultez, corrigez, validez les fiches ;
    archivez ou supprimez en lot.
  • « Tableau de bord »   : indicateurs (conformité, opérateurs, volumes…).
  • « Assistant IA »      : posez des questions en langage naturel sur
    vos données (ex. « combien de fiches validées cette semaine ? »).

------------------------------------------------------------------------
  ARRÊTER / REDÉMARRER
------------------------------------------------------------------------
  • Arrêter (les données sont conservées) :
        Windows : stop-windows.bat   ·   Mac : stop-mac.command
        Linux   : ./stop.sh
  • Redémarrer : relancez simplement le script Start.
  • Tout effacer et repartir de zéro : reset-all-data.sh (ou .bat).

------------------------------------------------------------------------
  NOTES
------------------------------------------------------------------------
  • Il s'agit d'une version de test, à faire tourner localement.
  • Rien n'est déployé sur un serveur ; fermer l'application = tout
    s'arrête sur votre poste.
  • En cas de souci, vérifiez que Docker Desktop est bien démarré, puis
    relancez le script Start.
========================================================================
